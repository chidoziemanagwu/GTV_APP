import requests
from bs4 import BeautifulSoup
import hashlib
import logging
import difflib
import re
from django.utils import timezone
from .models import PageVersion, Change, Notification, NotificationPreference, MonitoredPage, NotionScrapeLog

logger = logging.getLogger(__name__)

class NotionScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def scrape_page(self, page):
        """
        Scrape a Notion page and check for changes
        Returns a list of Change objects if changes were detected
        """
        try:
            response = requests.get(page.url, headers=self.headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.extract()

            # Get text content
            text = soup.get_text()

            # Calculate hash of content
            content_hash = hashlib.sha256(text.encode()).hexdigest()

            # Check if content has changed
            changes = []
            if page.content_hash and page.content_hash != content_hash:
                # Content has changed, create a PageVersion
                previous_version = PageVersion.objects.create(
                    url=page.url,
                    title=page.title,
                    content_text=text,
                    content_html=str(soup),
                    content_hash=page.content_hash
                )

                current_version = PageVersion.objects.create(
                    url=page.url,
                    title=page.title,
                    content_text=text,
                    content_html=str(soup),
                    content_hash=content_hash
                )

                # Generate diff
                diff = self._generate_diff(
                    previous_version.content_text,
                    current_version.content_text,
                    page.title
                )

                # Determine change type
                change_type = self._determine_change_type(
                    previous_version.content_text,
                    current_version.content_text
                )

                # Create a Change object
                change = Change.objects.create(
                    section=page.title,
                    url=page.url,
                    previous_version=previous_version,
                    current_version=current_version,
                    description=diff['summary'],
                    diff_text=diff['text_diff'],
                    diff_html=diff['html_diff'],
                    change_type=change_type
                )
                changes.append(change)

                # Create notifications for all users
                self._create_notifications(change)

            # Update the page's hash
            page.content_hash = content_hash
            page.save()

            return changes

        except Exception as e:
            logger.error(f"Error scraping {page.url}: {e}")
            raise

    def _generate_diff(self, old_text, new_text, title):
        """Generate a diff between old and new text"""
        # Split text into lines
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()

        # Generate diff
        diff = difflib.unified_diff(old_lines, new_lines, lineterm='')
        diff_text = '\n'.join(list(diff))

        # Generate HTML diff for display
        d = difflib.HtmlDiff()
        html_diff = d.make_file(old_lines, new_lines, title, title)

        # Generate a summary of changes
        summary = self._generate_summary(old_text, new_text)

        return {
            'text_diff': diff_text,
            'html_diff': html_diff,
            'summary': summary
        }

    def _generate_summary(self, old_text, new_text):
        """Generate a summary of changes"""
        # Count additions and removals
        old_words = len(re.findall(r'\w+', old_text))
        new_words = len(re.findall(r'\w+', new_text))

        if new_words > old_words:
            additions = new_words - old_words
            summary = f"Added approximately {additions} words"
        else:
            removals = old_words - new_words
            summary = f"Removed approximately {removals} words"

        # Check for specific changes in key sections
        key_phrases = [
            "eligibility criteria", "mandatory criteria", "optional criteria",
            "evidence", "document", "requirement", "deadline", "fee"
        ]

        for phrase in key_phrases:
            if phrase in new_text.lower() and phrase not in old_text.lower():
                summary += f". Added information about {phrase}"
            elif phrase in old_text.lower() and phrase not in new_text.lower():
                summary += f". Removed information about {phrase}"

        return summary

    def _determine_change_type(self, old_text, new_text):
        """Determine if a change is major or minor"""
        # Count words in both texts
        old_words = len(re.findall(r'\w+', old_text))
        new_words = len(re.findall(r'\w+', new_text))

        # Calculate percentage change
        word_diff = abs(new_words - old_words)
        percentage_change = (word_diff / old_words) * 100 if old_words > 0 else 100

        # Check for key phrases that would indicate a major change
        major_indicators = [
            "eligibility criteria", "mandatory criteria", "optional criteria",
            "evidence requirements", "application process", "deadline",
            "fee", "required documents"
        ]

        # Check if any major indicators are in the diff
        for indicator in major_indicators:
            if (indicator in new_text.lower() and indicator not in old_text.lower()) or \
               (indicator in old_text.lower() and indicator not in new_text.lower()):
                return 'major'

        # If percentage change is significant, it's a major change
        if percentage_change > 10:
            return 'major'

        return 'minor'

    def _create_notifications(self, change):
        """Create notifications for all users with in-app notifications enabled"""
        # Get users with notification preferences
        for pref in NotificationPreference.objects.filter(in_app_notifications=True):
            # Check if the user wants to be notified of this change type
            if not pref.notify_major_changes_only or change.change_type == 'major':
                Notification.objects.create(
                    user=pref.user,
                    change=change
                )