# payments/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.conf import settings
from django.http import HttpResponse
from .models import Payment
from expert_marketplace.models import Booking
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY

def process_payment(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)

    # Fixed consultation fee
    amount = 10000  # £100.00 in pence

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency='gbp',
            metadata={'booking_id': booking.id}
        )

        payment = Payment.objects.create(
            booking=booking,
            amount=amount/100,
            stripe_payment_intent_id=intent.id
        )

        return render(request, 'payments/payment.html', {
            'client_secret': intent.client_secret,
            'booking': booking,
            'STRIPE_PUBLIC_KEY': settings.STRIPE_PUBLIC_KEY
        })

    except stripe.error.StripeError as e:
        messages.error(request, "Payment processing error. Please try again.")
        return redirect('expert_marketplace:book_consultation')

def payment_success(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    payment = get_object_or_404(Payment, booking=booking)

    payment.status = 'completed'
    payment.save()

    booking.status = 'confirmed'
    booking.save()

    messages.success(request, "Payment successful! Your consultation has been confirmed.")
    return redirect('expert_marketplace:consultation_confirmation')

def payment_cancel(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    messages.warning(request, "Payment cancelled. Please try again.")
    return redirect('expert_marketplace:book_consultation')

def webhook(request):
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    payload = request.body
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        return HttpResponse(status=400)

    if event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        booking_id = payment_intent['metadata']['booking_id']

        try:
            booking = Booking.objects.get(id=booking_id)
            payment = Payment.objects.get(booking=booking)
            payment.status = 'completed'
            payment.save()

            booking.status = 'confirmed'
            booking.save()
        except (Booking.DoesNotExist, Payment.DoesNotExist):
            return HttpResponse(status=404)

    return HttpResponse(status=200)