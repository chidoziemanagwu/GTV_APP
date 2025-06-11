from django.utils import timezone
from django.db.models import Sum, Count
from datetime import datetime, timedelta
from .models import Expert, ExpertEarning, ExpertBonus, Booking

def calculate_monthly_bonus_pool():
    """Calculate the monthly bonus pool for experts"""
    # Get total platform fees for the month
    start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    total_platform_fees = Booking.objects.filter(
        status='completed',
        completed_at__gte=start_of_month
    ).aggregate(total=Sum('platform_fee'))['total'] or 0
    
    # Allocate 20% of platform fees to bonus pool
    return total_platform_fees * 0.20

def distribute_monthly_bonuses():
    """Distribute monthly bonuses to experts based on performance"""
    bonus_pool = calculate_monthly_bonus_pool()
    if bonus_pool <= 0:
        return []
    
    # Get active experts with at least one completed consultation this month
    start_of_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    experts = Expert.objects.filter(
        is_active=True,
        bookings__status='completed',
        bookings__completed_at__gte=start_of_month
    ).distinct()
    
    if not experts.exists():
        return []
    
    # Calculate performance metrics for each expert
    expert_metrics = []
    for expert in experts:
        # Count completed consultations this month
        completed_count = expert.bookings.filter(
            status='completed',
            completed_at__gte=start_of_month
        ).count()
        
        # Calculate average rating
        completed_bookings = expert.bookings.filter(
            status='completed',
            completed_at__gte=start_of_month
        )
        
        total_rating = 0
        rated_count = 0
        
        for booking in completed_bookings:
            try:
                if booking.consultation and booking.consultation.rating:
                    total_rating += booking.consultation.rating
                    rated_count += 1
            except:
                pass
        
        avg_rating = total_rating / rated_count if rated_count > 0 else 0
        
        # Calculate performance score (weighted by consultations and rating)
        performance_score = completed_count * (1 + avg_rating / 5)
        
        expert_metrics.append({
            'expert': expert,
            'completed_count': completed_count,
            'avg_rating': avg_rating,
            'performance_score': performance_score
        })
    
    # Sort by performance score
    expert_metrics.sort(key=lambda x: x['performance_score'], reverse=True)
    
    # Calculate total performance score
    total_score = sum(metric['performance_score'] for metric in expert_metrics)
    
    # Distribute bonus based on performance score ratio
    bonuses_created = []
    for metric in expert_metrics:
        if total_score > 0:
            bonus_share = (metric['performance_score'] / total_score) * bonus_pool
        else:
            bonus_share = 0
        
        if bonus_share >= 1:  # Only create bonuses worth at least $1
            bonus = ExpertBonus.objects.create(
                expert=metric['expert'],
                amount=bonus_share,
                reason='Monthly Performance Bonus',
                description=f"Based on {metric['completed_count']} consultations with average rating {metric['avg_rating']:.1f}/5"
            )
            bonuses_created.append(bonus)
    
    return bonuses_created

def update_expert_tiers():
    """Update expert tiers based on performance metrics"""
    experts = Expert.objects.filter(is_active=True)
    for expert in experts:
        expert.update_tier()
    return experts

def process_completed_consultation(booking):
    """Process financial aspects of a completed consultation"""
    if booking.status != 'completed' or not booking.expert:
        return None
    
    # Ensure financials are calculated
    if not booking.expert_earnings or not booking.platform_fee:
        booking.calculate_financials()
    
    # Create earning record
    earning, created = ExpertEarning.objects.get_or_create(
        booking=booking,
        expert=booking.expert,
        defaults={
            'amount': booking.expert_earnings,
            'platform_fee': booking.platform_fee,
            'status': 'pending'
        }
    )
    
    if created:
        # Update expert stats
        expert = booking.expert
        expert.total_earnings += booking.expert_earnings
        expert.pending_payout += booking.expert_earnings
        expert.lifetime_consultations += 1
        
        # Update monthly stats
        expert.update_monthly_stats()
        expert.monthly_consultations += 1
        
        expert.save()
    
    return earning