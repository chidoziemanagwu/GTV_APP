# expert_marketplace/assignment_engine.py

import datetime
import json
import logging
from django.utils import timezone
from django.conf import settings
from django.db.models import Count, Q
from .models import Expert, Booking

logger = logging.getLogger(__name__)

class SmartAssignmentEngine:
    def is_expert_available(self, expert, booking_datetime_aware, booking_duration_minutes, booking_instance=None):
        """
        Checks if an expert is available for a given booking time and duration,
        considering their defined availability slots and existing bookings.
        booking_instance is the booking being scheduled/rescheduled. If provided,
        it's excluded from conflict checks.
        """
        logger.debug(
            f"[Expert {expert.id} ({expert.full_name})] Checking availability for booking starting at {booking_datetime_aware} "
            f"(duration: {booking_duration_minutes} mins). Booking ID: {booking_instance.id if booking_instance else 'New'}"
        )

        try:
            availability_slots = json.loads(expert.availability_json or '[]')
            if not isinstance(availability_slots, list):
                logger.warning(f"[Expert {expert.id}] availability_json was not a list, defaulting to empty. Value: {expert.availability_json}")
                availability_slots = []
        except json.JSONDecodeError:
            logger.error(f"Invalid availability_json for expert {expert.id}: {expert.availability_json}")
            return False

        if not availability_slots:
            logger.info(f"[Expert {expert.id}] No availability slots defined in availability_json.")
            return False
      
        logger.debug(f"[Expert {expert.id}] Parsed availability_slots: {availability_slots}")

        booking_end_datetime_aware = booking_datetime_aware + datetime.timedelta(minutes=booking_duration_minutes)

        for slot_idx, slot_data in enumerate(availability_slots):
            slot_date_str = slot_data.get('date')
            slot_start_time_str = slot_data.get('start_time')
            slot_end_time_str = slot_data.get('end_time')

            if not (slot_date_str and slot_start_time_str and slot_end_time_str):
                logger.warning(f"[Expert {expert.id}] Slot #{slot_idx} is malformed: {slot_data}. Skipping.")
                continue

            try:
                slot_date_naive = datetime.datetime.strptime(slot_date_str, '%Y-%m-%d').date()
                slot_start_time_naive = datetime.datetime.strptime(slot_start_time_str, '%H:%M').time()
                slot_end_time_naive = datetime.datetime.strptime(slot_end_time_str, '%H:%M').time()
            except ValueError as e:
                logger.error(f"[Expert {expert.id}] Error parsing date/time in slot #{slot_idx}: {slot_data}. Error: {e}. Skipping.")
                continue

            try:
                # Ensure timezone information is correctly applied based on settings
                if settings.USE_TZ:
                    expert_slot_start_dt_aware = timezone.make_aware(
                        datetime.datetime.combine(slot_date_naive, slot_start_time_naive),
                        timezone.get_default_timezone() # Or expert's specific timezone if available
                    )
                    expert_slot_end_dt_aware = timezone.make_aware(
                        datetime.datetime.combine(slot_date_naive, slot_end_time_naive),
                        timezone.get_default_timezone() # Or expert's specific timezone
                    )
                else:
                    expert_slot_start_dt_aware = datetime.datetime.combine(slot_date_naive, slot_start_time_naive)
                    expert_slot_end_dt_aware = datetime.datetime.combine(slot_date_naive, slot_end_time_naive)

            except (OverflowError, ValueError) as e: 
                logger.error(f"[Expert {expert.id}] Error making slot datetime aware for slot #{slot_idx} ({slot_data}): {e}. Skipping.")
                continue
          
            logger.debug(
                f"[Expert {expert.id}] Slot #{slot_idx}: Parsed as {expert_slot_start_dt_aware} - {expert_slot_end_dt_aware} (Aware: {settings.USE_TZ})"
            )

            # Check if the booking window fits within the expert's defined slot
            if not (expert_slot_start_dt_aware <= booking_datetime_aware and \
                    booking_end_datetime_aware <= expert_slot_end_dt_aware):
                logger.debug(
                    f"[Expert {expert.id}] Slot #{slot_idx}: Booking window {booking_datetime_aware} - {booking_end_datetime_aware} "
                    f"does NOT fit within this slot {expert_slot_start_dt_aware} - {expert_slot_end_dt_aware}."
                )
                continue 

            logger.info(
                f"[Expert {expert.id}] Slot #{slot_idx}: Booking window FITS within this slot. "
                f"Now checking for conflicts..."
            )

            # Check for conflicting bookings for this expert within this slot
            current_booking_id_to_exclude = booking_instance.id if booking_instance and booking_instance.id else None
          
            # We need to check conflicts against the specific date of the booking_datetime_aware
            # because an expert's slot might span multiple days (though unlikely with current format)
            # or the booking_datetime_aware might be for a specific occurrence within a recurring slot (future feature).
            # For now, using booking_datetime_aware.date() is correct for non-recurring slots.
            conflicting_bookings_qs = Booking.objects.filter(
                expert=expert,
                scheduled_date=booking_datetime_aware.date(), # Check conflicts on the specific date of the slot
                status__in=['confirmed', 'pending_payment', 'assigned'] # Consider active bookings
            )
            if current_booking_id_to_exclude:
                conflicting_bookings_qs = conflicting_bookings_qs.exclude(id=current_booking_id_to_exclude)

            is_slot_truly_free = True
            for existing_booking in conflicting_bookings_qs:
                if not (existing_booking.scheduled_date and existing_booking.scheduled_time):
                    logger.warning(f"Existing booking {existing_booking.id} has no scheduled_time, skipping overlap check.")
                    continue

                ex_bk_start_naive = datetime.datetime.combine(existing_booking.scheduled_date, existing_booking.scheduled_time)
                ex_bk_duration = existing_booking.duration_minutes or settings.CONSULTATION_DURATION_MINUTES # Fallback duration
              
                try:
                    if settings.USE_TZ:
                        ex_bk_start_aware = timezone.make_aware(ex_bk_start_naive, timezone.get_default_timezone())
                    else:
                        ex_bk_start_aware = ex_bk_start_naive
                except (OverflowError, ValueError) as e:
                     logger.error(f"Error making existing booking {existing_booking.id} start time aware: {e}. Skipping conflict check for this one.")
                     continue
                ex_bk_end_aware = ex_bk_start_aware + datetime.timedelta(minutes=ex_bk_duration)
              
                # Standard overlap check: (StartA < EndB) and (EndA > StartB)
                if booking_datetime_aware < ex_bk_end_aware and booking_end_datetime_aware > ex_bk_start_aware:
                    logger.info(
                        f"[Expert {expert.id}] Slot #{slot_idx}: CONFLICTS with existing booking {existing_booking.id} "
                        f"({ex_bk_start_aware} - {ex_bk_end_aware})."
                    )
                    is_slot_truly_free = False
                    break # Conflict found, no need to check other existing bookings for this slot

            if is_slot_truly_free:
                logger.info(
                    f"[Expert {expert.id}] Slot #{slot_idx} ({expert_slot_start_dt_aware} - {expert_slot_end_dt_aware}) "
                    f"IS AVAILABLE for booking {booking_datetime_aware} - {booking_end_datetime_aware}. No conflicts."
                )
                return True # Expert is available in this slot
            else: 
                logger.info(f"[Expert {expert.id}] Slot #{slot_idx} fits but has conflicts. Trying next slot.")

        # If loop completes, no suitable slot was found or all had conflicts
        logger.info(f"[Expert {expert.id}] All slots checked. None are suitable or free for the requested time.")
        return False

    def assign_expert(self, booking, expert_to_exclude_id=None):
        """
        Assigns the best available expert for a given booking at its scheduled time.
        Can exclude a specific expert by ID.
        Returns (expert, error_message_or_none)
        """
        log_message_prefix = (
            f"Attempting to assign expert for booking ID {booking.id} "
            f"(User: {booking.user}, Expertise: {booking.get_expertise_needed_display()}, "
            f"Time: {booking.scheduled_date} {booking.scheduled_time})"
        )
        if expert_to_exclude_id is not None:
            log_message_prefix += f", EXCLUDING expert ID {expert_to_exclude_id}"
        else:
            log_message_prefix += ", no expert explicitly excluded."
        logger.info(log_message_prefix)
      
        potential_experts_qs = Expert.objects.filter(
            is_active=True,
            expertise=booking.expertise_needed
        )
        logger.debug(f"Initial potential_experts_qs count for expertise '{booking.get_expertise_needed_display()}': {potential_experts_qs.count()}")
        
        if expert_to_exclude_id is not None:
            logger.info(f"Applying exclusion for expert ID {expert_to_exclude_id}.")
            potential_experts_qs = potential_experts_qs.exclude(id=expert_to_exclude_id)
            logger.debug(f"Potential_experts_qs count AFTER excluding ID {expert_to_exclude_id}: {potential_experts_qs.count()}")
      
        potential_experts = potential_experts_qs.annotate(
            num_bookings=Count('bookings', filter=Q(bookings__status__in=['confirmed', 'completed']))
        ).order_by('last_assigned_at', '-rating', 'num_bookings') # Prioritize less recently assigned, higher rated, fewer bookings
      
        final_expert_ids_to_consider = [exp.id for exp in potential_experts]
        logger.info(f"Final list of {len(final_expert_ids_to_consider)} expert IDs to consider for assignment: {final_expert_ids_to_consider}")

        if not potential_experts.exists():
            msg = f"No experts found matching expertise '{booking.get_expertise_needed_display()}' (after exclusions if any)."
            logger.warning(msg)
            return None, msg

        if not (booking.scheduled_date and booking.scheduled_time):
            msg = f"Booking {booking.id} is missing scheduled_date or scheduled_time."
            logger.error(msg)
            return None, msg

        booking_datetime_naive = datetime.datetime.combine(booking.scheduled_date, booking.scheduled_time)
      
        try:
            if settings.USE_TZ:
                booking_datetime_aware = timezone.make_aware(booking_datetime_naive, timezone.get_default_timezone())
            else:
                booking_datetime_aware = booking_datetime_naive 
        except (OverflowError, ValueError) as e: 
            msg = f"Error making booking datetime aware for booking {booking.id} ({booking_datetime_naive}): {e}"
            logger.error(msg)
            return None, "There was an issue processing the requested booking time due to timezone conversion. Please try a slightly different time."

        logger.debug(f"Booking datetime (aware for checks): {booking_datetime_aware}, Duration: {booking.duration_minutes} mins")

        for expert_candidate in potential_experts:
            logger.debug(f"Considering expert ID {expert_candidate.id} ({expert_candidate.full_name}), Rating: {expert_candidate.rating}, Last Assigned: {expert_candidate.last_assigned_at}")
            if self.is_expert_available(expert_candidate, booking_datetime_aware, booking.duration_minutes, booking_instance=booking):
                logger.info(f"Successfully assigned Expert ID {expert_candidate.id} ({expert_candidate.full_name}) to Booking ID {booking.id}")
                # The calling function should handle saving the expert to the booking and updating last_assigned_at
                return expert_candidate, None 
            else:
                logger.debug(f"Expert ID {expert_candidate.id} ({expert_candidate.full_name}) is not available for Booking ID {booking.id} at the requested time.")
      
        msg = f"All other experts with {booking.get_expertise_needed_display()} expertise are booked at {booking.scheduled_date} {booking.scheduled_time} or do not have this specific slot available."
        logger.warning(f"Failed to assign any expert for Booking ID {booking.id} (after exclusions if any). {msg}")
        return None, msg

    def _find_alternative_slot_for_booking(self, booking, expert_to_exclude_id):
        """
        Helper method to find an alternative expert and slot for a booking.
        Iterates through experts (excluding one) and their available slots.
        Returns (expert, new_date, new_time) or (None, None, None)
        """
        logger.info(f"Searching for alternative slot for Booking ID {booking.id}, excluding Expert ID {expert_to_exclude_id}")
        potential_experts_qs = Expert.objects.filter(
            is_active=True,
            expertise=booking.expertise_needed
        ).exclude(id=expert_to_exclude_id).annotate(
            num_bookings=Count('bookings', filter=Q(bookings__status__in=['confirmed', 'completed']))
        ).order_by('last_assigned_at', '-rating', 'num_bookings')

        if not potential_experts_qs.exists():
            logger.warning(f"No alternative experts found for expertise '{booking.get_expertise_needed_display()}' when excluding {expert_to_exclude_id}.")
            return None, None, None

        for expert_candidate in potential_experts_qs:
            logger.debug(f"Checking alternative slots for Expert ID {expert_candidate.id} ({expert_candidate.full_name})")
            try:
                availability_slots = json.loads(expert_candidate.availability_json or '[]')
                if not isinstance(availability_slots, list): availability_slots = []
            except json.JSONDecodeError:
                logger.error(f"Invalid availability_json for expert {expert_candidate.id} during alternative search: {expert_candidate.availability_json}")
                continue # Skip this expert

            if not availability_slots:
                logger.debug(f"Expert {expert_candidate.id} has no availability slots for alternative search.")
                continue

            for slot_data in availability_slots:
                slot_date_str = slot_data.get('date')
                slot_start_time_str = slot_data.get('start_time')
                # slot_end_time_str = slot_data.get('end_time') # Not directly needed for start check

                if not (slot_date_str and slot_start_time_str):
                    logger.warning(f"[Expert {expert_candidate.id}] Malformed slot in alternative search: {slot_data}. Skipping.")
                    continue
                
                try:
                    potential_date_naive = datetime.datetime.strptime(slot_date_str, '%Y-%m-%d').date()
                    potential_time_naive = datetime.datetime.strptime(slot_start_time_str, '%H:%M').time()
                except ValueError as e:
                    logger.error(f"[Expert {expert_candidate.id}] Error parsing date/time in slot for alternative search: {slot_data}. Error: {e}. Skipping.")
                    continue

                # Create aware datetime for the potential new slot start
                potential_booking_datetime_naive = datetime.datetime.combine(potential_date_naive, potential_time_naive)
                try:
                    if settings.USE_TZ:
                        potential_booking_datetime_aware = timezone.make_aware(potential_booking_datetime_naive, timezone.get_default_timezone())
                    else:
                        potential_booking_datetime_aware = potential_booking_datetime_naive
                except (OverflowError, ValueError) as e:
                    logger.error(f"Error making potential_booking_datetime_aware for expert {expert_candidate.id}, slot {slot_data}: {e}")
                    continue
                
                # Check if this potential new slot is in the future (or today but future time)
                if potential_booking_datetime_aware <= timezone.now(): # Ensure we don't book in the past
                    logger.debug(f"Skipping past or current slot for Expert {expert_candidate.id}: {potential_booking_datetime_aware}")
                    continue

                if self.is_expert_available(expert_candidate, potential_booking_datetime_aware, booking.duration_minutes, booking_instance=booking):
                    logger.info(f"Found alternative slot for Booking ID {booking.id} with Expert ID {expert_candidate.id} at {potential_date_naive} {potential_time_naive}")
                    return expert_candidate, potential_date_naive, potential_time_naive
        
        logger.info(f"No alternative slots found for Booking ID {booking.id} after checking all other experts.")
        return None, None, None

    def reassign_expert_after_cancellation(self, original_booking, cancelling_expert_id):
        """
        Attempts to reassign a booking after an expert cancellation.
        1. Tries to find another expert for the same time.
        2. If not found, tries to find another expert for any of their available times.
        Returns a tuple: (status_code, new_expert, new_date, new_time, message)
        status_code can be: "REASSIGNED_SAME_TIME", "REASSIGNED_NEW_TIME", "REFUND_REQUIRED"
        """
        logger.info(f"Reassignment process started for Booking ID {original_booking.id} due to cancellation by Expert ID {cancelling_expert_id}.")

        # --- Attempt 1: Same time, different expert (same expertise) ---
        logger.info(f"Attempt 1: Searching for expert at original time {original_booking.scheduled_date} {original_booking.scheduled_time}, excluding Expert ID {cancelling_expert_id}")
        new_expert_same_time, error_msg_s1 = self.assign_expert(original_booking, expert_to_exclude_id=cancelling_expert_id)

        if new_expert_same_time:
            logger.info(f"Attempt 1 SUCCESS: Found Expert ID {new_expert_same_time.id} for original time.")
            # The calling view will update original_booking.expert, original_booking.status, etc.
            # and new_expert_same_time.last_assigned_at
            return "REASSIGNED_SAME_TIME", new_expert_same_time, original_booking.scheduled_date, original_booking.scheduled_time, \
                   f"Reassigned to {new_expert_same_time.full_name} for the original time."

        logger.info(f"Attempt 1 FAILED: No expert found for original time. Message: {error_msg_s1}")

        # --- Attempt 2: Different time, different expert (same expertise) ---
        logger.info(f"Attempt 2: Searching for alternative slot with any other suitable expert, excluding Expert ID {cancelling_expert_id}")
        alt_expert, alt_date, alt_time = self._find_alternative_slot_for_booking(original_booking, cancelling_expert_id)

        if alt_expert and alt_date and alt_time:
            logger.info(f"Attempt 2 SUCCESS: Found alternative slot with Expert ID {alt_expert.id} at {alt_date} {alt_time}.")
            # The calling view will need to:
            # 1. Potentially confirm this new time with the user.
            # 2. Update original_booking.expert, .scheduled_date, .scheduled_time, .status
            # 3. Update alt_expert.last_assigned_at
            return "REASSIGNED_NEW_TIME", alt_expert, alt_date, alt_time, \
                   f"Found alternative: {alt_expert.full_name} available on {alt_date} at {alt_time}. User confirmation may be needed."

        logger.info("Attempt 2 FAILED: No alternative expert or slot found.")

        # --- All attempts failed ---
        logger.warning(f"Reassignment FAILED for Booking ID {original_booking.id}. Proceeding to recommend refund.")
        return "REFUND_REQUIRED", None, None, None, \
               "We couldn't find another expert for the original time or a suitable alternative. A refund will be processed."