from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.utils import timezone
from .models import Change, Notification, MonitoredPage, NotionScrapeLog
from .scraper import NotionScraper
import logging

logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    """Show the Notion monitor dashboard"""
    # Get recent changes
    recent_changes = Change.objects.all().order_by('-detected_at')[:10]

    # Get monitored pages
    monitored_pages = MonitoredPage.objects.all().order_by('title')

    # Get unread notifications for the user
    unread_notifications = Notification.objects.filter(
        user=request.user,
        read=False
    ).order_by('-created_at')

    # Get the latest scrape log
    try:
        latest_log = NotionScrapeLog.objects.latest('started_at')
    except NotionScrapeLog.DoesNotExist:
        latest_log = None

    return render(request, 'notion_monitor/dashboard.html', {
        'recent_changes': recent_changes,
        'monitored_pages': monitored_pages,
        'unread_notifications': unread_notifications,
        'latest_log': latest_log
    })

@login_required
def change_list(request):
    """Show a list of all detected changes"""
    changes = Change.objects.all().order_by('-detected_at')

    # Get unread notifications count
    unread_count = Notification.objects.filter(user=request.user, read=False).count()

    return render(request, 'notion_monitor/change_list.html', {
        'changes': changes,
        'unread_count': unread_count
    })

@login_required
def change_detail(request, change_id):
    """Show details of a specific change"""
    change = get_object_or_404(Change, id=change_id)

    # Mark any notifications for this change as read
    Notification.objects.filter(
        user=request.user,
        change=change,
        read=False
    ).update(read=True)

    return render(request, 'notion_monitor/change_detail.html', {
        'change': change
    })

@login_required
def notification_list(request):
    """Show user's notifications"""
    notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')

    # Get notification preferences or create default ones
    try:
        from django.db.models import Model
        # Check if NotificationPreference model exists
        if 'NotificationPreference' in globals() and issubclass(globals()['NotificationPreference'], Model):
            preferences = NotificationPreference.objects.get(user=request.user)
        else:
            # Create a simple preferences dict if model doesn't exist
            preferences = {
                'email_notifications': True,
                'in_app_notifications': True,
                'notify_major_changes_only': False
            }
    except (ImportError, NameError):
        # Create a simple preferences dict if model doesn't exist
        preferences = {
            'email_notifications': True,
            'in_app_notifications': True,
            'notify_major_changes_only': False
        }
    except Exception as e:
        logger.error(f"Error getting notification preferences: {e}")
        preferences = {
            'email_notifications': True,
            'in_app_notifications': True,
            'notify_major_changes_only': False
        }

    return render(request, 'notion_monitor/notification_list.html', {
        'notifications': notifications,
        'preferences': preferences
    })

@login_required
def mark_notification_read(request, notification_id):
    """Mark a notification as read"""
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.read = True
    notification.save()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    else:
        return redirect('notion_monitor:notification_list')

@login_required
def mark_all_read(request):
    """Mark all notifications as read"""
    Notification.objects.filter(user=request.user, read=False).update(read=True)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    else:
        return redirect('notion_monitor:notification_list')

@login_required
def toggle_notifications(request):
    """Toggle notification preferences"""
    if request.method == 'POST':
        try:
            from django.db.models import Model
            # Check if NotificationPreference model exists
            if 'NotificationPreference' in globals() and issubclass(globals()['NotificationPreference'], Model):
                try:
                    preferences = NotificationPreference.objects.get(user=request.user)
                except NotificationPreference.DoesNotExist:
                    preferences = NotificationPreference.objects.create(user=request.user)

                # Update preferences
                preferences.email_notifications = request.POST.get('email_notifications') == 'on'
                preferences.in_app_notifications = request.POST.get('in_app_notifications') == 'on'
                preferences.notify_major_changes_only = request.POST.get('notify_major_changes_only') == 'on'
                preferences.save()

                messages.success(request, "Notification preferences updated successfully.")
        except (ImportError, NameError):
            # Just show a message if model doesn't exist
            messages.info(request, "Notification preferences feature is not fully implemented yet.")
        except Exception as e:
            logger.error(f"Error updating notification preferences: {e}")
            messages.error(request, "An error occurred while updating preferences.")

    return redirect('notion_monitor:notification_list')

@login_required
def add_monitored_page(request):
    """Add a new page to monitor"""
    if request.method == 'POST':
        url = request.POST.get('url')
        title = request.POST.get('title')

        if url and title:
            # Create the monitored page
            page = MonitoredPage.objects.create(
                url=url,
                title=title
            )

            # Initialize the scraper and get the initial content
            scraper = NotionScraper()
            try:
                scraper.scrape_page(page)
                return redirect('notion_monitor:dashboard')
            except Exception as e:
                logger.error(f"Error scraping page: {e}")
                return render(request, 'notion_monitor/add_page.html', {
                    'error': f"Error scraping page: {str(e)}",
                    'url': url,
                    'title': title
                })
        else:
            return render(request, 'notion_monitor/add_page.html', {
                'error': "URL and title are required",
                'url': url,
                'title': title
            })

    return render(request, 'notion_monitor/add_page.html')

@login_required
def remove_monitored_page(request, page_id):
    """Remove a page from monitoring"""
    page = get_object_or_404(MonitoredPage, id=page_id)
    page.delete()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    else:
        return redirect('notion_monitor:dashboard')

@login_required
def manual_check(request):
    """Manually trigger a check for changes"""
    log = NotionScrapeLog.objects.create(
        status='in_progress'
    )

    try:
        scraper = NotionScraper()
        pages = MonitoredPage.objects.all()

        changes_count = 0
        for page in pages:
            try:
                changes = scraper.scrape_page(page)
                changes_count += len(changes)
                log.pages_checked += 1
            except Exception as e:
                logger.error(f"Error scraping page {page.title}: {e}")

        log.changes_detected = changes_count
        log.status = 'completed'
        log.completed_at = timezone.now()
        log.save()

        messages.success(request, f"Check complete. Found {changes_count} changes.")
        return redirect('notion_monitor:dashboard')
    except Exception as e:
        logger.error(f"Error during manual check: {e}")
        log.status = 'failed'
        log.error_message = str(e)
        log.completed_at = timezone.now()
        log.save()

        messages.error(request, f"Error checking for changes: {str(e)}")
        return redirect('notion_monitor:dashboard')