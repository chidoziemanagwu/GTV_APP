import stripe
from django.conf import settings
from .models import SubscriptionPlan, Subscription, Payment, Booking
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

def create_stripe_customer(user):
    """Create a Stripe customer for a user"""
    try:
        customer = stripe.Customer.create(
            email=user.email,
            name=f"{user.first_name} {user.last_name}",
            metadata={
                'user_id': user.id
            }
        )

        # Save the Stripe customer ID to the user's profile
        profile = user.userprofile
        profile.stripe_customer_id = customer.id
        profile.save()

        return customer
    except Exception as e:
        print(f"Error creating Stripe customer: {e}")
        return None

def get_or_create_stripe_customer(user):
    """Get or create a Stripe customer for a user"""
    try:
        profile = user.userprofile

        if profile.stripe_customer_id:
            # Try to retrieve the customer
            try:
                customer = stripe.Customer.retrieve(profile.stripe_customer_id)
                return customer
            except stripe.error.InvalidRequestError:
                # Customer doesn't exist, create a new one
                return create_stripe_customer(user)
        else:
            # No customer ID, create a new one
            return create_stripe_customer(user)
    except Exception as e:
        print(f"Error getting/creating Stripe customer: {e}")
        return None

def create_subscription_checkout_session(user, plan_id, success_url, cancel_url):
    """Create a Stripe checkout session for a subscription"""
    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)

        # Get or create Stripe customer
        customer = get_or_create_stripe_customer(user)

        if not customer:
            return None

        # Create checkout session
        if plan.billing_cycle == 'one_time':
            # One-time payment
            checkout_session = stripe.checkout.Session.create(
                customer=customer.id,
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'gbp',
                        'product_data': {
                            'name': plan.name,
                            'description': plan.features.replace('\n', ', '),
                        },
                        'unit_amount': int(plan.price * 100),  # Convert to cents
                        'recurring': None,  # One-time payment
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    'user_id': user.id,
                    'plan_id': plan.id,
                    'payment_type': 'subscription',
                }
            )
        else:
            # Recurring subscription
            interval = 'week' if plan.billing_cycle == 'weekly' else 'month'

            checkout_session = stripe.checkout.Session.create(
                customer=customer.id,
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'gbp',
                        'product_data': {
                            'name': plan.name,
                            'description': plan.features.replace('\n', ', '),
                        },
                        'unit_amount': int(plan.price * 100),  # Convert to cents
                        'recurring': {
                            'interval': interval,
                        },
                    },
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    'user_id': user.id,
                    'plan_id': plan.id,
                    'payment_type': 'subscription',
                }
            )

        return checkout_session
    except Exception as e:
        print(f"Error creating subscription checkout session: {e}")
        return None

def create_service_checkout_session(user, service_id, scheduled_time, success_url, cancel_url):
    """Create a Stripe checkout session for an expert service"""
    try:
        from expert_marketplace.models import Service
        service = Service.objects.get(id=service_id)

        # Get or create Stripe customer
        customer = get_or_create_stripe_customer(user)

        if not customer:
            return None

        # Create checkout session
        checkout_session = stripe.checkout.Session.create(
            customer=customer.id,
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'gbp',
                    'product_data': {
                        'name': service.name,
                        'description': f"{service.description} - {service.duration_minutes} minutes",
                    },
                    'unit_amount': int(service.price * 100),  # Convert to cents
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': user.id,
                'service_id': service.id,
                'expert_id': service.expert.id,
                'scheduled_time': scheduled_time.isoformat(),
                'payment_type': 'service',
            }
        )

        return checkout_session
    except Exception as e:
        print(f"Error creating service checkout session: {e}")
        return None

def handle_subscription_webhook(event):
    """Handle Stripe subscription webhook events"""
    try:
        # Get the webhook data
        subscription = event.data.object

        # Get the user from metadata
        user_id = subscription.metadata.get('user_id')
        plan_id = subscription.metadata.get('plan_id')

        if not user_id or not plan_id:
            print("Missing user_id or plan_id in metadata")
            return False

        user = User.objects.get(id=user_id)
        plan = SubscriptionPlan.objects.get(id=plan_id)

        # Handle different event types
        if event.type == 'checkout.session.completed':
            # Create subscription record
            Subscription.objects.create(
                user=user,
                plan=plan,
                status='active',
                stripe_subscription_id=subscription.id,
            )

            # Create payment record
            Payment.objects.create(
                user=user,
                amount=plan.price,
                currency='GBP',
                payment_type='subscription',
                status='completed',
                stripe_payment_id=subscription.payment_intent,
                subscription=subscription,
            )

            return True

        elif event.type == 'customer.subscription.updated':
            # Update subscription status
            try:
                sub = Subscription.objects.get(stripe_subscription_id=subscription.id)
                sub.status = subscription.status
                sub.save()
                return True
            except Subscription.DoesNotExist:
                print(f"Subscription not found: {subscription.id}")
                return False

        elif event.type == 'customer.subscription.deleted':
            # Cancel subscription
            try:
                sub = Subscription.objects.get(stripe_subscription_id=subscription.id)
                sub.status = 'canceled'
                sub.is_active = False
                sub.save()
                return True
            except Subscription.DoesNotExist:
                print(f"Subscription not found: {subscription.id}")
                return False

        return False
    except Exception as e:
        print(f"Error handling subscription webhook: {e}")
        return False

def handle_service_webhook(event):
    """Handle Stripe service payment webhook events"""
    try:
        # Get the webhook data
        session = event.data.object

        # Get the metadata
        user_id = session.metadata.get('user_id')
        service_id = session.metadata.get('service_id')
        expert_id = session.metadata.get('expert_id')
        scheduled_time = session.metadata.get('scheduled_time')

        if not user_id or not service_id or not expert_id or not scheduled_time:
            print("Missing metadata in service webhook")
            return False

        from expert_marketplace.models import Service, Expert
        user = User.objects.get(id=user_id)
        service = Service.objects.get(id=service_id)
        expert = Expert.objects.get(id=expert_id)

        # Handle checkout.session.completed event
        if event.type == 'checkout.session.completed':
            # Create payment record
            payment = Payment.objects.create(
                user=user,
                amount=service.price,
                currency='GBP',
                payment_type='service',
                status='completed',
                stripe_payment_id=session.payment_intent,
                service=service,
            )

            # Create booking record
            from datetime import datetime
            scheduled_datetime = datetime.fromisoformat(scheduled_time)

            Booking.objects.create(
                user=user,
                expert=expert,
                service=service,
                payment=payment,
                status='confirmed',
                scheduled_time=scheduled_datetime,
            )

            return True

        return False
    except Exception as e:
        print(f"Error handling service webhook: {e}")
        return False