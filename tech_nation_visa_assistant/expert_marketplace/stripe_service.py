# expert_marketplace/stripe_service.py
import stripe
from django.conf import settings
from .models import Booking, ExpertEarning, Expert # Ensure Expert is imported
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation 
import logging

logger = logging.getLogger(__name__)

DEFAULT_CURRENCY = getattr(settings, 'STRIPE_CURRENCY', 'gbp')
stripe.api_key = settings.STRIPE_SECRET_KEY

class StripePaymentService:
    def __init__(self):
        self.api_key = settings.STRIPE_SECRET_KEY
        self.currency = DEFAULT_CURRENCY
        stripe.api_key = self.api_key

    # ... (your existing create_payment_intent, confirm_payment, process_refund methods) ...
    # PASTE YOUR EXISTING create_payment_intent, confirm_payment, and process_refund methods here
    # For brevity, I'm not repeating them. Ensure _update_expert_earning_after_refund is also present.

    def create_payment_intent(self, booking):
        try:
            consultation_fee_decimal = Decimal(str(booking.consultation_fee))
            amount_cents = int(consultation_fee_decimal * 100)
          
            if amount_cents <= 0:
                logger.error(f"Attempted to create payment intent with zero or negative amount for booking {booking.id}.")
                return {'success': False, 'error': "Payment amount must be greater than zero."}

            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=self.currency,
                metadata={
                    'booking_id': str(booking.id),
                    'customer_email': booking.email,
                    'customer_name': booking.name,
                    'expertise_needed': booking.get_expertise_needed_display() or booking.expertise_needed or "N/A"
                },
                receipt_email=booking.email,
                description=f"Consultation Booking ID: {booking.id} for {booking.get_expertise_needed_display() or booking.expertise_needed or 'consultation'}"
            )
          
            booking.stripe_payment_intent_id = intent.id
            booking.save(update_fields=['stripe_payment_intent_id'])
          
            logger.info(f"PaymentIntent {intent.id} created for booking {booking.id}, amount {amount_cents} {self.currency.upper()}.")
            return {
                'success': True,
                'client_secret': intent.client_secret,
                'payment_intent_id': intent.id
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error creating payment intent for booking {booking.id}: {str(e)}")
            return {'success': False, 'error': f"Stripe error: {str(e)}"}
        except Exception as e:
            logger.error(f"Generic error creating payment intent for booking {booking.id}: {str(e)}")
            return {'success': False, 'error': f"An unexpected error occurred: {str(e)}"}

    def confirm_payment(self, payment_intent_id):
        try:
            if not payment_intent_id:
                logger.error("confirm_payment called with no payment_intent_id.")
                return {'success': False, 'error': "Payment Intent ID is required."}

            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            logger.info(f"Retrieved PaymentIntent {payment_intent_id} for confirmation. Status: {payment_intent.status}")
          
            if payment_intent.status == 'succeeded':
                charge_id = None
                if hasattr(payment_intent, 'latest_charge') and payment_intent.latest_charge:
                    charge_id = payment_intent.latest_charge
                elif payment_intent.charges and payment_intent.charges.data:
                    successful_charges = [ch for ch in payment_intent.charges.data if ch.status == 'succeeded']
                    if successful_charges:
                        charge_id = sorted(successful_charges, key=lambda ch: ch.created, reverse=True)[0].id
              
                if charge_id:
                    logger.info(f"PaymentIntent {payment_intent_id} confirmed successfully. Charge ID: {charge_id}")
                    return {'success': True, 'charge_id': charge_id, 'status': payment_intent.status}
                else:
                    logger.warning(f"PaymentIntent {payment_intent_id} succeeded but no charge_id could be extracted.")
                    return {'success': True, 'charge_id': None, 'status': payment_intent.status, 'warning': "PaymentIntent succeeded, but charge_id could not be extracted."}
            else:
                logger.warning(f"PaymentIntent {payment_intent_id} not succeeded. Status: {payment_intent.status}")
                return {'success': False, 'error': f"Payment not succeeded. Status: {payment_intent.status}", 'status': payment_intent.status}
        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error confirming payment_intent {payment_intent_id}: {str(e)}")
            return {'success': False, 'error': f"Stripe error: {str(e)}"}
        except Exception as e:
            logger.error(f"Generic error confirming payment_intent {payment_intent_id}: {str(e)}")
            return {'success': False, 'error': f"An unexpected error occurred: {str(e)}"}

    def process_refund(self, booking, refund_percentage=1.0, reason_code="requested_by_customer", custom_reason_details=""):
        try:
            if not isinstance(booking, Booking):
                logger.error("process_refund called with invalid booking object.")
                return {'success': False, 'error': "Invalid booking object provided."}

            if not booking.stripe_charge_id and booking.stripe_payment_intent_id:
                logger.info(f"Booking {booking.id} has no stripe_charge_id. Attempting to retrieve from PaymentIntent {booking.stripe_payment_intent_id}.")
                try:
                    pi = stripe.PaymentIntent.retrieve(booking.stripe_payment_intent_id)
                    charge_id_from_pi = None
                    if hasattr(pi, 'latest_charge') and pi.latest_charge:
                        charge_id_from_pi = pi.latest_charge
                    elif pi.charges and pi.charges.data:
                        successful_charges = [ch for ch in pi.charges.data if ch.status == 'succeeded']
                        if successful_charges:
                            charge_id_from_pi = sorted(successful_charges, key=lambda ch: ch.created, reverse=True)[0].id
                  
                    if charge_id_from_pi:
                        booking.stripe_charge_id = charge_id_from_pi
                        booking.save(update_fields=['stripe_charge_id'])
                        logger.info(f"Retrieved and saved stripe_charge_id {booking.stripe_charge_id} for booking {booking.id}.")
                    else:
                        logger.warning(f"Could not retrieve charge_id from payment_intent {booking.stripe_payment_intent_id} for booking {booking.id}.")
                except Exception as e_pi:
                    logger.error(f"Error retrieving charge_id from payment_intent {booking.stripe_payment_intent_id} for booking {booking.id}: {str(e_pi)}")

            if not booking.stripe_charge_id:
                logger.error(f"No stripe_charge_id found for booking {booking.id} to process refund. Recording refund locally.")
                consultation_fee_decimal_local = Decimal(str(booking.consultation_fee))
                intended_refund_decimal_local = (consultation_fee_decimal_local * Decimal(str(refund_percentage))).quantize(Decimal('0.01'), ROUND_HALF_UP)
              
                current_total_refunded_on_booking = booking.refund_amount or Decimal('0.00')
                new_total_refunded_on_booking = (current_total_refunded_on_booking + intended_refund_decimal_local).quantize(Decimal('0.01'), ROUND_HALF_UP)
              
                fields_to_update_no_charge = set()
                if new_total_refunded_on_booking > consultation_fee_decimal_local: 
                    new_total_refunded_on_booking = consultation_fee_decimal_local
              
                booking.refund_amount = new_total_refunded_on_booking
                fields_to_update_no_charge.add('refund_amount')

                if new_total_refunded_on_booking >= consultation_fee_decimal_local:
                    booking.status = 'refunded'
                elif new_total_refunded_on_booking > Decimal('0.00'):
                    booking.status = 'partially_refunded'
                else: 
                    if booking.status not in ['cancelled', 'refunded', 'partially_refunded']:
                         booking.status = 'cancelled' 
                fields_to_update_no_charge.add('status')
              
                if custom_reason_details:
                    booking.cancellation_reason = custom_reason_details
                    fields_to_update_no_charge.add('cancellation_reason')
                if booking.status in ['refunded', 'partially_refunded', 'cancelled'] and not booking.cancelled_at:
                    booking.cancelled_at = timezone.now()
                    fields_to_update_no_charge.add('cancelled_at')
                if booking.status in ['refunded', 'partially_refunded'] and not booking.refund_processed_at:
                    booking.refund_processed_at = timezone.now() 
                    fields_to_update_no_charge.add('refund_processed_at')

                booking.save(update_fields=list(fields_to_update_no_charge))
                self._update_expert_earning_after_refund(booking) 

                return {
                    'success': True, 
                    'message': "No charge ID found for Stripe refund. Payment might not have been completed or charge ID was not stored. Refund recorded locally.",
                    'refund_amount': float(intended_refund_decimal_local), 
                    'total_refunded_on_booking': float(booking.refund_amount),
                    'stripe_status': 'n/a_no_charge_id'
                }
          
            consultation_fee_decimal = Decimal(str(booking.consultation_fee))
            this_refund_operation_amount_decimal = (consultation_fee_decimal * Decimal(str(refund_percentage))).quantize(Decimal('0.01'), ROUND_HALF_UP)
            already_refunded_on_booking = booking.refund_amount or Decimal('0.00')
            refundable_amount_left = (consultation_fee_decimal - already_refunded_on_booking).quantize(Decimal('0.01'), ROUND_HALF_UP)
            actual_amount_to_refund_this_op = min(this_refund_operation_amount_decimal, refundable_amount_left)
            actual_amount_to_refund_this_op = max(actual_amount_to_refund_this_op, Decimal('0.00')) 

            amount_cents = int(actual_amount_to_refund_this_op * 100)

            if amount_cents <= 0: 
                logger.info(f"Calculated refund amount for this operation is zero or less ({amount_cents} cents) for booking {booking.id}. No Stripe refund processed for this operation.")
                fields_to_update_booking_on_zero_op = set()
                original_consultation_fee = Decimal(str(booking.consultation_fee))
                current_total_refunded = booking.refund_amount or Decimal('0.00')
                new_status_on_zero_op = booking.status 
                if current_total_refunded >= original_consultation_fee:
                    new_status_on_zero_op = 'refunded'
                elif current_total_refunded > Decimal('0.00'):
                    new_status_on_zero_op = 'partially_refunded'
                elif booking.status not in ['cancelled', 'refunded', 'partially_refunded', 'completed']:
                    if custom_reason_details and "cancel" in custom_reason_details.lower():
                         new_status_on_zero_op = 'cancelled'

                if booking.status != new_status_on_zero_op:
                    booking.status = new_status_on_zero_op
                    fields_to_update_booking_on_zero_op.add('status')

                if booking.status in ['refunded', 'partially_refunded', 'cancelled'] and not booking.cancelled_at:
                    booking.cancelled_at = timezone.now()
                    fields_to_update_booking_on_zero_op.add('cancelled_at')
              
                if custom_reason_details and (not booking.cancellation_reason or booking.cancellation_reason != custom_reason_details):
                    booking.cancellation_reason = custom_reason_details
                    fields_to_update_booking_on_zero_op.add('cancellation_reason')
              
                if booking.refund_amount is None:
                    booking.refund_amount = Decimal('0.00')
                    fields_to_update_booking_on_zero_op.add('refund_amount')
              
                if fields_to_update_booking_on_zero_op:
                    booking.save(update_fields=list(fields_to_update_booking_on_zero_op))
              
                self._update_expert_earning_after_refund(booking) 

                return {
                    'success': True, 
                    'message': "Refund amount for this specific operation is zero or less. No new Stripe refund processed. Local booking records have been updated/verified.",
                    'refund_id': None, 
                    'refund_amount': 0.0, 
                    'total_refunded_on_booking': float(booking.refund_amount or Decimal('0.00')),
                    'stripe_status': 'n/a_zero_amount_for_this_op' 
                }

            valid_stripe_reasons = ['duplicate', 'fraudulent', 'requested_by_customer']
            if reason_code not in valid_stripe_reasons:
                logger.warning(f"Invalid Stripe reason_code '{reason_code}' provided. Defaulting to 'requested_by_customer'.")
                reason_code = 'requested_by_customer'

            logger.info(f"Attempting Stripe refund for booking {booking.id}, charge {booking.stripe_charge_id}, amount {amount_cents} cents ({self.currency.upper()}), Stripe reason: {reason_code}")
          
            stripe_refund_obj = stripe.Refund.create(
                charge=booking.stripe_charge_id,
                amount=amount_cents,
                reason=reason_code,
                metadata={
                    'booking_id': str(booking.id),
                    'op_refund_pct_orig_fee': str(refund_percentage), 
                    'amount_refunded_this_op': str(actual_amount_to_refund_this_op),
                    'original_consultation_fee': str(consultation_fee_decimal),
                    'custom_reason_details': custom_reason_details[:480] if custom_reason_details else ""
                }
            )
          
            amount_refunded_from_stripe = Decimal(str(stripe_refund_obj.amount / 100.0))
            logger.info(f"Stripe refund successful for booking {booking.id}. Refund ID: {stripe_refund_obj.id}, Status: {stripe_refund_obj.status}, Amount Refunded by Stripe: {amount_refunded_from_stripe} {stripe_refund_obj.currency.upper()}")

            booking.refund_amount = (already_refunded_on_booking + amount_refunded_from_stripe).quantize(Decimal('0.01'), ROUND_HALF_UP)
          
            if booking.refund_amount >= consultation_fee_decimal:
                booking.status = 'refunded'
            elif booking.refund_amount > Decimal('0.00'):
                booking.status = 'partially_refunded'

            booking.stripe_refund_id = stripe_refund_obj.id 
            booking.refund_processed_at = timezone.now() 
            if custom_reason_details:
                booking.cancellation_reason = custom_reason_details
          
            fields_to_update = {'status', 'refund_amount', 'stripe_refund_id', 'refund_processed_at'}
            if custom_reason_details: fields_to_update.add('cancellation_reason')
            if booking.status in ['refunded', 'partially_refunded', 'cancelled'] and not booking.cancelled_at:
                booking.cancelled_at = timezone.now()
                fields_to_update.add('cancelled_at')
          
            booking.save(update_fields=list(fields_to_update))
            self._update_expert_earning_after_refund(booking)

            return {
                'success': True,
                'refund_id': stripe_refund_obj.id,
                'refund_amount': float(amount_refunded_from_stripe), 
                'total_refunded_on_booking': float(booking.refund_amount),
                'stripe_status': stripe_refund_obj.status
            }

        except stripe.error.StripeError as e:
            error_code = e.code if hasattr(e, 'code') else 'N/A'
            error_msg = f"Stripe API error during refund for booking {booking.id if booking else 'N/A'}: {str(e)}. Code: {error_code}"
            logger.error(error_msg)

            if error_code == 'charge_already_refunded':
                logger.warning(f"Charge {booking.stripe_charge_id if booking else 'N/A'} for booking {booking.id if booking else 'N/A'} was already fully refunded on Stripe. Verifying local status.")
                consultation_fee_decimal = Decimal(str(booking.consultation_fee)) if booking else Decimal('0.00')
                fields_to_update_already_refunded = set()

                if booking.status != 'refunded':
                    booking.status = 'refunded'
                    fields_to_update_already_refunded.add('status')
              
                if booking.refund_amount is None or booking.refund_amount < consultation_fee_decimal:
                    booking.refund_amount = consultation_fee_decimal 
                    fields_to_update_already_refunded.add('refund_amount')

                if not booking.cancelled_at:
                    booking.cancelled_at = timezone.now()
                    fields_to_update_already_refunded.add('cancelled_at')
                if not booking.refund_processed_at: 
                    booking.refund_processed_at = timezone.now()
                    fields_to_update_already_refunded.add('refund_processed_at')
              
                current_cancellation_reason = booking.cancellation_reason or ""
                already_refunded_note = "Confirmed already fully refunded by Stripe."
                if already_refunded_note not in current_cancellation_reason:
                    new_reason = f"{current_cancellation_reason} {already_refunded_note}".strip()
                    booking.cancellation_reason = new_reason
                    fields_to_update_already_refunded.add('cancellation_reason')

                if fields_to_update_already_refunded:
                    try:
                        booking.save(update_fields=list(fields_to_update_already_refunded))
                        logger.info(f"Local booking {booking.id} record updated to reflect 'already fully refunded' status from Stripe.")
                    except Exception as save_err:
                        logger.error(f"Failed to update local booking {booking.id} after 'charge_already_refunded' error: {save_err}")
              
                self._update_expert_earning_after_refund(booking) 
              
                return {
                    'success': True, 
                    'message': f"Charge was already fully refunded on Stripe. Local booking record updated/verified. Stripe message: {getattr(e, 'user_message', str(e))}",
                    'refund_id': booking.stripe_refund_id, 
                    'refund_amount': float(booking.refund_amount or consultation_fee_decimal),
                    'total_refunded_on_booking': float(booking.refund_amount or consultation_fee_decimal),
                    'stripe_status': 'already_refunded' 
                }
          
            user_message = getattr(e, 'user_message', str(e))
            return {'success': False, 'error': f"Stripe error: {user_message}"}
        except Exception as e:
            logger.error(f"Generic error during refund processing for booking {booking.id if booking else 'N/A'}: {str(e)}", exc_info=True)
            return {'success': False, 'error': f"An unexpected error occurred: {str(e)}"}

    def _update_expert_earning_after_refund(self, booking):
        try:
            earning = ExpertEarning.objects.filter(booking=booking).first()
            if not earning:
                logger.info(f"No ExpertEarning record found for booking {booking.id} to update after refund.")
                return

            if not booking.expert:
                logger.warning(f"Booking {booking.id} has no expert assigned. Cannot calculate expert earnings for refund adjustment.")
                if earning.status != 'cancelled': 
                    earning.amount = Decimal('0.00')
                    earning.status = 'cancelled'
                    earning.save(update_fields=['amount', 'status'])
                    logger.info(f"Cancelled ExpertEarning for booking {booking.id} due to missing expert during refund adjustment.")
                return

            original_consultation_fee = Decimal(str(booking.consultation_fee))
            total_refunded_amount = booking.refund_amount or Decimal('0.00')
            effective_consultation_fee = (original_consultation_fee - total_refunded_amount).quantize(Decimal('0.01'), ROUND_HALF_UP)
            effective_consultation_fee = max(effective_consultation_fee, Decimal('0.00')) 

            expert_commission_rate = Decimal(str(booking.expert.commission_rate))
            new_expert_earning_amount = (effective_consultation_fee * (Decimal('1.00') - expert_commission_rate)).quantize(Decimal('0.01'), ROUND_HALF_UP)
            new_expert_earning_amount = max(new_expert_earning_amount, Decimal('0.00'))

            fields_to_update_earning = set()
          
            if earning.amount != new_expert_earning_amount:
                # Store old amount if needed for aggregate updates
                old_amount = earning.amount
                earning.amount = new_expert_earning_amount
                fields_to_update_earning.add('amount')

                # Adjust expert's aggregates
                amount_difference = new_expert_earning_amount - old_amount
                expert_profile = booking.expert
                expert_profile.total_earnings = (expert_profile.total_earnings or Decimal('0.00')) + amount_difference
                if earning.status == ExpertEarning.PENDING: # Only adjust pending if it was pending
                    expert_profile.pending_payout = (expert_profile.pending_payout or Decimal('0.00')) + amount_difference
                expert_profile.save(update_fields=['total_earnings', 'pending_payout'])


            if effective_consultation_fee <= Decimal('0.00') or new_expert_earning_amount <= Decimal('0.00'):
                if earning.status != 'cancelled':
                    if earning.status == ExpertEarning.PENDING: # If it was pending and now cancelled
                        expert_profile = booking.expert
                        expert_profile.pending_payout = (expert_profile.pending_payout or Decimal('0.00')) - earning.amount # Subtract the old amount
                        expert_profile.pending_payout = max(Decimal('0.00'), expert_profile.pending_payout)
                        expert_profile.save(update_fields=['pending_payout'])
                    
                    earning.status = 'cancelled'
                    fields_to_update_earning.add('status')
            elif earning.status == 'cancelled' and new_expert_earning_amount > Decimal('0.00'):
                earning.status = 'pending' 
                fields_to_update_earning.add('status')
                # If moving from cancelled to pending, adjust aggregates
                expert_profile = booking.expert
                expert_profile.pending_payout = (expert_profile.pending_payout or Decimal('0.00')) + new_expert_earning_amount
                expert_profile.save(update_fields=['pending_payout'])


            if fields_to_update_earning:
                earning.save(update_fields=list(fields_to_update_earning))
                logger.info(f"ExpertEarning for booking {booking.id} updated. New amount: {earning.amount}, New status: {earning.status}")
            else:
                logger.info(f"ExpertEarning for booking {booking.id} required no update after refund processing. Amount: {earning.amount}, Status: {earning.status}")

        except Exception as ee:
            logger.error(f"Error in _update_expert_earning_after_refund for booking {booking.id}: {str(ee)}", exc_info=True)

    # NEW METHOD
    def create_transfer(self, expert_stripe_account_id, amount_decimal, description="", metadata=None):
        if not expert_stripe_account_id:
            logger.error("create_transfer called with no expert_stripe_account_id.")
            return {'success': False, 'error': "Expert's Stripe Account ID is required."}
        
        if not isinstance(amount_decimal, Decimal) or amount_decimal <= Decimal('0.00'):
            logger.error(f"create_transfer called with invalid amount: {amount_decimal}")
            return {'success': False, 'error': "Transfer amount must be a positive Decimal."}

        amount_cents = int(amount_decimal * 100)
        if amount_cents <= 0:
            logger.error(f"create_transfer: amount_cents is zero or negative ({amount_cents}) for amount_decimal {amount_decimal}")
            return {'success': False, 'error': "Transfer amount in cents must be greater than zero."}

        try:
            transfer = stripe.Transfer.create(
                amount=amount_cents,
                currency=self.currency,
                destination=expert_stripe_account_id,
                description=description or f"Payout to expert {expert_stripe_account_id}",
                metadata=metadata or {}
            )
            logger.info(f"Stripe Transfer {transfer.id} created for expert {expert_stripe_account_id}, amount {amount_cents} {self.currency.upper()}. Status: {transfer.status}")
            return {
                'success': True,
                'transfer_id': transfer.id,
                'status': transfer.status,
                'amount_transferred': Decimal(transfer.amount) / 100, # Amount confirmed by Stripe
                'currency': transfer.currency
            }
        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error creating transfer for expert {expert_stripe_account_id}: {str(e)}")
            return {'success': False, 'error': f"Stripe error: {str(e)}"}
        except Exception as e:
            logger.error(f"Generic error creating transfer for expert {expert_stripe_account_id}: {str(e)}")
            return {'success': False, 'error': f"An unexpected error occurred: {str(e)}"}


    def get_account_details(self, stripe_account_id):
        """
        Retrieves the Stripe Account object for the given stripe_account_id.
        Returns the Stripe Account object on success, None on failure.
        """
        if not stripe_account_id:
            logger.error("get_account_details called with no stripe_account_id.")
            return None
        try:
            account = stripe.Account.retrieve(stripe_account_id)
            logger.info(f"Successfully retrieved Stripe account details for {stripe_account_id}")
            return account
        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error retrieving account {stripe_account_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Generic error retrieving account {stripe_account_id}: {str(e)}")
            return None
        
# --- Standalone wrapper functions ---
# (Your existing standalone wrappers: create_payment_intent, confirm_payment, process_refund)
# Ensure they call the class methods.

def create_payment_intent(booking):
    service = StripePaymentService()
    return service.create_payment_intent(booking)

def confirm_payment(payment_intent_id):
    service = StripePaymentService()
    confirmation_details = service.confirm_payment(payment_intent_id)
    if confirmation_details and confirmation_details['success']:
        try:
            booking = Booking.objects.filter(stripe_payment_intent_id=payment_intent_id).first()
            if booking:
                fields_to_update_booking = set()
                if confirmation_details.get('charge_id') and booking.stripe_charge_id != confirmation_details['charge_id']:
                    booking.stripe_charge_id = confirmation_details['charge_id']
                    fields_to_update_booking.add('stripe_charge_id')
                if booking.status == 'pending_payment':
                    booking.status = 'confirmed'
                    fields_to_update_booking.add('status')
                if fields_to_update_booking:
                    booking.save(update_fields=list(fields_to_update_booking))
                    logger.info(f"Booking {booking.id} updated via standalone confirm_payment wrapper.")
            else:
                logger.warning(f"Standalone confirm_payment: No booking found for PI {payment_intent_id} to update.")
        except Exception as e_booking_update:
            logger.error(f"Standalone confirm_payment: Error updating booking for PI {payment_intent_id}: {str(e_booking_update)}")
    return confirmation_details

def process_refund(booking, amount_decimal=None, reason_code=None, custom_reason_details=None, reason=None):
    service = StripePaymentService()
    if not isinstance(booking, Booking):
        logger.error("process_refund (standalone) called with invalid booking object.")
        return False, {"error": "Invalid booking object provided."}

    consultation_fee = Decimal(str(booking.consultation_fee))
    refund_percentage_float = 1.0 

    if amount_decimal is not None:
        try:
            actual_amount_to_refund_this_op = Decimal(str(amount_decimal))
            if actual_amount_to_refund_this_op < Decimal('0.00'):
                return False, {"error": "Refund amount cannot be negative."}
            if consultation_fee > Decimal('0.00'):
                refund_percentage_float = float(actual_amount_to_refund_this_op / consultation_fee)
            elif actual_amount_to_refund_this_op > Decimal('0.00'):
                refund_percentage_float = 1.0 
            else: 
                refund_percentage_float = 0.0
        except InvalidOperation:
            logger.error(f"Invalid amount_decimal '{amount_decimal}' for booking {booking.id}.")
            return False, {"error": "Invalid refund amount format."}
  
    refund_percentage_float = max(0.0, min(1.0, refund_percentage_float))
    final_reason_code = 'requested_by_customer' 
    if reason_code and reason_code in ['duplicate', 'fraudulent', 'requested_by_customer']:
        final_reason_code = reason_code
    elif reason: 
        if "duplicate" in reason.lower(): final_reason_code = 'duplicate'
        elif "fraud" in reason.lower(): final_reason_code = 'fraudulent'
  
    final_custom_details = custom_reason_details if custom_reason_details is not None else reason
    if final_custom_details is None: final_custom_details = "Refund processed via system."
    final_custom_details = final_custom_details[:480] if final_custom_details else ""

    result_dict = service.process_refund(
        booking, 
        refund_percentage=refund_percentage_float, 
        reason_code=final_reason_code,
        custom_reason_details=final_custom_details
    )
  
    if result_dict.get('success', False):
        return True, result_dict
    else:
        error_message = result_dict.get('error', "An unknown error occurred during refund.")
        if 'error' not in result_dict: result_dict['error'] = error_message
        return False, result_dict

# NEW STANDALONE WRAPPER FOR TRANSFER (optional, but good for consistency)
def create_stripe_transfer(expert_stripe_account_id, amount_decimal, description="", metadata=None):
    service = StripePaymentService()
    return service.create_transfer(expert_stripe_account_id, amount_decimal, description, metadata)




def process_expert_payouts(expert_profile, earnings_to_pay, is_instant_request=False, payout_description="Platform Payout"):
    """
    Processes payout for a list of ExpertEarning records.
    Updates ExpertEarning statuses, Expert model totals, and initiates Stripe Transfer.
    """
    if not isinstance(expert_profile, Expert): # Type check
        logger.error(f"process_expert_payouts called with invalid expert_profile type: {type(expert_profile)}")
        return {'success': False, 'error': "Invalid expert profile provided."}

    if not expert_profile.stripe_account_id:
        logger.error(f"Cannot process payout for expert {expert_profile.id} ({expert_profile.full_name}): Stripe account ID missing.")
        return {'success': False, 'error': "Expert's Stripe Account ID is missing."}

    if not earnings_to_pay:
        logger.info(f"No earnings provided to pay out for expert {expert_profile.id} ({expert_profile.full_name}).")
        return {'success': True, 'message': "No earnings to pay out."}

    valid_earnings = [e for e in earnings_to_pay if isinstance(e, ExpertEarning) and e.status == ExpertEarning.PENDING and e.amount > Decimal('0.00')]
    if not valid_earnings:
        logger.info(f"No valid, pending, positive earnings to pay out for expert {expert_profile.id} ({expert_profile.full_name}).")
        # Mark zero/negative pending earnings as cancelled if any were passed
        for earning in earnings_to_pay:
            if earning.status == ExpertEarning.PENDING and earning.amount <= Decimal('0.00'):
                earning.status = ExpertEarning.CANCELLED
                earning.notes = (earning.notes or "") + " Voided at payout processing due to zero/negative amount."
                earning.save(update_fields=['status', 'notes'])
                # Adjust expert aggregates if this earning was contributing to pending_payout
                expert_profile.pending_payout = (expert_profile.pending_payout or Decimal('0.00')) - earning.amount # Subtract original amount
                expert_profile.pending_payout = max(Decimal('0.00'), expert_profile.pending_payout)
                # total_earnings should also be reduced by this earning.amount
                expert_profile.total_earnings = (expert_profile.total_earnings or Decimal('0.00')) - earning.amount
                expert_profile.save(update_fields=['pending_payout', 'total_earnings'])
        return {'success': True, 'message': "No valid earnings to process for payout."}

    total_payout_amount_gross = sum(earning.amount for earning in valid_earnings)
    
    instant_payout_fee = Decimal('2.00') if is_instant_request else Decimal('0.00')
    net_payout_amount = total_payout_amount_gross - instant_payout_fee

    if net_payout_amount <= Decimal('0.00'):
        logger.warning(f"Net payout amount for expert {expert_profile.id} ({expert_profile.full_name}) is zero or less. Gross: {total_payout_amount_gross}, Fee: {instant_payout_fee}. No payout processed.")
        # If it's an instant request that failed due to fee, the error message is specific.
        # For weekly payouts (fee is 0), this means gross was 0.
        error_msg = f"Payout amount (£{net_payout_amount:.2f}) is too low."
        if is_instant_request and instant_payout_fee > Decimal('0.00'):
            error_msg += f" This may be due to the £{instant_payout_fee:.2f} fee. Gross earnings for this payout: £{total_payout_amount_gross:.2f}."
        else:
            error_msg += f" Gross earnings for this payout: £{total_payout_amount_gross:.2f}."
        return {'success': False, 'error': error_msg}

    # Check Stripe account readiness
    try:
        stripe_account = stripe.Account.retrieve(expert_profile.stripe_account_id)
        if not stripe_account.payouts_enabled:
            logger.error(f"Payouts disabled for Stripe account {expert_profile.stripe_account_id} (Expert {expert_profile.id}). Please ensure your Stripe account is fully verified and active.")
            return {'success': False, 'error': "Expert's Stripe account does not have payouts enabled. Please check your Stripe dashboard."}
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error checking account {expert_profile.stripe_account_id} for expert {expert_profile.id}: {str(e)}")
        return {'success': False, 'error': f"Stripe error checking account status: {str(e)}"}
    except Exception as e: # Catch any other unexpected error
        logger.error(f"Unexpected error checking Stripe account {expert_profile.stripe_account_id} for expert {expert_profile.id}: {str(e)}")
        return {'success': False, 'error': f"Unexpected error checking Stripe account status: {str(e)}"}


    # Create Stripe Transfer
    stripe_service = StripePaymentService()
    transfer_metadata = {
        'expert_id': str(expert_profile.id),
        'expert_email': expert_profile.email,
        'earnings_ids': ",".join([str(e.id) for e in valid_earnings]),
        'is_instant_request': str(is_instant_request),
        'gross_amount_payout_batch': str(total_payout_amount_gross),
        'fee_applied_to_batch': str(instant_payout_fee)
    }
    
    # Use the description passed in, or construct a default if not provided
    final_transfer_description = payout_description 
    if not final_transfer_description: # Fallback if somehow empty
        final_transfer_description = f"Payout for {expert_profile.full_name}. Gross: {total_payout_amount_gross}"
        if is_instant_request and instant_payout_fee > Decimal('0.00'):
            final_transfer_description += f", Fee: {instant_payout_fee}, Net: {net_payout_amount}"
        # For weekly, net_payout_amount will be same as total_payout_amount_gross if fee is 0
    
    transfer_result = stripe_service.create_transfer(
        expert_stripe_account_id=expert_profile.stripe_account_id,
        amount_decimal=net_payout_amount,
        description=final_transfer_description[:255], # Stripe description limit
        metadata=transfer_metadata
    )

    if transfer_result.get('success'):
        transfer_id = transfer_result.get('transfer_id')
        paid_at_time = timezone.now()
        amount_actually_transferred = transfer_result.get('amount_transferred', net_payout_amount)

        for earning_obj in valid_earnings:
            earning_obj.status = ExpertEarning.PAID
            earning_obj.transaction_id = transfer_id
            earning_obj.paid_at = paid_at_time
            
            current_notes = (earning_obj.notes or "").strip()
            payout_batch_note = ""
            if is_instant_request and instant_payout_fee > Decimal('0.00'):
                 payout_batch_note = f" Part of instant payout batch. Total gross: £{total_payout_amount_gross:.2f}. £{instant_payout_fee:.2f} fee applied to batch."
            else: # For weekly payouts
                 payout_batch_note = f" Part of scheduled weekly payout batch. Total gross for batch: £{total_payout_amount_gross:.2f}."
            
            if payout_batch_note not in current_notes: # Avoid duplicate notes
                earning_obj.notes = f"{current_notes} {payout_batch_note}".strip()
            
            earning_obj.save(update_fields=['status', 'transaction_id', 'paid_at', 'notes'])

        # ... (Update Expert model totals - this logic seems okay) ...
        
        logger.info(f"Successfully processed payout transfer {transfer_id} for expert {expert_profile.id} ({expert_profile.full_name}). Net amount: {amount_actually_transferred}")
        return {'success': True, 'transfer_id': transfer_id, 'message': f"Payout of £{amount_actually_transferred:.2f} processed successfully. Transfer ID: {transfer_id}"}
    else:
        # ... (error handling) ...
        return {'success': False, 'error': f"Stripe transfer failed: {transfer_result.get('error', 'Unknown transfer error')}"}