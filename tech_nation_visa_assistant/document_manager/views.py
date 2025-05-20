from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, FileResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from django.db.models import F
from datetime import datetime
import json
import os
import io
import logging
import re
import threading
import time
import concurrent.futures
# Rename the docx Document import to avoid conflict with your model
from docx import Document as DocxDocument
import PyPDF2
from .models import Document
from .forms import DocumentForm, PersonalStatementForm, CVForm
from .services import GeminiDocumentGenerator
from openai import OpenAI
from django.conf import settings
from bs4 import BeautifulSoup
import requests
from .utils import calculate_application_progress
from functools import wraps
import uuid
from typing import Optional


# Configure logging
logger = logging.getLogger(__name__)

class AIProvider:
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.deepseek_client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
    def format_personal_statement(self, content: str) -> str:
        """Format the personal statement with proper HTML and styling"""
        # First create the wrapper with styling
        html_template = """
        <div class="personal-statement" style="max-width: 800px; margin: 0 auto; padding: 20px; font-family: Arial, sans-serif; line-height: 1.6;">
            <div class="warning-box" style="background-color: #fff3cd; border: 1px solid #ffeeba; padding: 15px; margin-bottom: 20px; border-radius: 5px;">
                <h4 style="color: #856404; margin-top: 0;">⚠️ SAMPLE STATEMENT</h4>
                <p>This is an AI-generated sample personal statement. You should:</p>
                <ul>
                    <li>Customize it with your specific achievements and experiences</li>
                    <li>Verify all facts and claims before submission</li>
                    <li>Use it as a guide, not a final submission</li>
                </ul>
            </div>

            {content}

            <div class="disclaimer-box" style="background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 15px; margin-top: 20px; border-radius: 5px;">
                <h4 style="color: #721c24; margin-top: 0;">📝 Important Notice</h4>
                <p>This document was generated based on the provided CV and instructions. Before submitting:</p>
                <ul>
                    <li>Review all content for accuracy</li>
                    <li>Replace all placeholder text [in brackets]</li>
                    <li>Ensure all claims are supported by evidence</li>
                    <li>Verify word count meets requirements</li>
                </ul>
            </div>
        </div>
        """

        # Convert markdown to HTML with custom styling
        import re

        # Replace markdown headers with styled HTML
        content = re.sub(r'# (.*)', r'<h1 style="color: #dc3545; text-align: center; font-size: 24px; margin-bottom: 30px;">\1</h1>', content)
        content = re.sub(r'## (.*)', r'<h2 style="color: #333; font-size: 20px; margin-top: 25px;">\1</h2>', content)
        content = re.sub(r'### (.*)', r'<h3 style="color: #444; font-size: 18px; margin-top: 20px;">\1</h3>', content)

        # Convert bold text
        content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)

        # Convert blockquotes
        content = re.sub(r'> (.*)', r'<div style="background-color: #e9ecef; border-left: 4px solid #dee2e6; padding: 15px; margin: 15px 0;">\1</div>', content)

        # Convert horizontal rules
        content = re.sub(r'---', '<hr style="margin: 25px 0; border: 0; border-top: 1px solid #eee;">', content)

        # Convert bullet points
        content = re.sub(r'- (.*)', r'<li style="margin-bottom: 8px;">\1</li>', content)
        content = content.replace('<li', '<ul style="margin-left: 20px; margin-bottom: 15px;"><li')
        content = content.replace('</li>\n</ul>', '</li></ul>')

        # Convert paragraphs
        paragraphs = content.split('\n\n')
        content = ''.join([f'<p style="margin-bottom: 15px;">{p}</p>' if not (p.startswith('<h') or p.startswith('<div') or p.startswith('<ul')) else p for p in paragraphs])

        # Insert the formatted content into the template
        return html_template.format(content=content)

    def try_deepseek(self, prompt: str) -> Optional[str]:
        """Try to get a response from DeepSeek"""
        try:
            response = self.deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": """You are an expert at writing personal statements for Tech Nation Global Talent Visa applications.

                    Format your response with proper structure, using:
                    - Main sections with # (like "# Introduction")
                    - Subsections with ## (like "## Technical Skills")
                    - Bold text for emphasis using **text**
                    - Bullet points using - for lists

                    Your personal statement should:
                    - Demonstrate exceptional talent and potential in digital technology
                    - Showcase technical skills, innovations, and impact
                    - Include specific examples of projects, achievements, and contributions
                    - Highlight recognition, awards, or publications
                    - Demonstrate potential to become a leader in the UK tech sector
                    - Include evidence of contributions to company/organizational growth
                    - Explain plans to contribute to the UK's digital technology sector
                    - Be clear, concise, and well-structured
                    - Ensure all claims can be supported by evidence
                    - Be approximately 800-1000 words

                    Make sure to include Introduction, Technical Expertise, Leadership, and Conclusion sections."""},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error with DeepSeek API: {str(e)}")
            return None

    def try_openai(self, prompt: str) -> Optional[str]:
        """Try to get a response from OpenAI"""
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": """You are an expert at writing personal statements for Tech Nation Global Talent Visa applications.

                    Format your response with proper structure, using:
                    - Main sections with # (like "# Introduction")
                    - Subsections with ## (like "## Technical Skills")
                    - Bold text for emphasis using **text**
                    - Bullet points using - for lists

                    Your personal statement should:
                    - Demonstrate exceptional talent and potential in digital technology
                    - Showcase technical skills, innovations, and impact
                    - Include specific examples of projects, achievements, and contributions
                    - Highlight recognition, awards, or publications
                    - Demonstrate potential to become a leader in the UK tech sector
                    - Include evidence of contributions to company/organizational growth
                    - Explain plans to contribute to the UK's digital technology sector
                    - Be clear, concise, and well-structured
                    - Ensure all claims can be supported by evidence
                    - Be approximately 800-1000 words

                    Make sure to include Introduction, Technical Expertise, Leadership, and Conclusion sections."""},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error with OpenAI API: {str(e)}")
            return None
            
        

    def generate_content(self, prompt: str) -> Optional[str]:
        """Try DeepSeek first, fall back to OpenAI if DeepSeek fails"""
        # Try DeepSeek first
        content = self.try_deepseek(prompt)
        if content:
            logger.info("Successfully generated content using DeepSeek")
            return content

        # Fall back to OpenAI if DeepSeek fails
        logger.info("DeepSeek failed, trying OpenAI")
        content = self.try_openai(prompt)
        if content:
            logger.info("Successfully generated content using OpenAI")
            return content

        # If both fail, return None
        logger.error("Both DeepSeek and OpenAI failed to generate content")
        return None



# Create a singleton instance
ai_provider = AIProvider()



# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Create a document cache
document_cache = {}

# Rate limiting decorator
def rate_limit(max_calls=5, window=60):
    """Decorator to limit API calls"""
    def decorator(view_func):
        # Use a simple in-memory store for rate limiting
        # In production, you'd use Redis or another shared cache
        calls = {}

        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Get user identifier
            user_id = request.user.id if request.user.is_authenticated else request.META.get('REMOTE_ADDR')
            key = f"{view_func.__name__}:{user_id}"

            # Get current timestamp
            now = time.time()

            # Initialize or clean up old timestamps
            if key not in calls:
                calls[key] = []
            calls[key] = [t for t in calls[key] if now - t < window]

            # Check if rate limit exceeded
            if len(calls[key]) >= max_calls:
                return JsonResponse({
                    'success': False,
                    'error': f'Rate limit exceeded. Maximum {max_calls} calls per {window} seconds.'
                }, status=429)

            # Add current call
            calls[key].append(now)

            # Process the view
            return view_func(request, *args, **kwargs)

        return _wrapped_view
    return decorator

# Background processing
class DocumentProcessor:
    @staticmethod
    def process_in_background(func, *args, **kwargs):
        """Run a function in a background thread"""
        thread = threading.Thread(target=func, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()
        return thread

def process_content_for_frontend(content):
    """Process the AI-generated content into properly formatted HTML with guidelines"""
    import re

    # Create a properly formatted HTML structure
    html_output = """
    <div class="personal-statement">
    """

    # Extract title and author if present
    title_match = re.search(r'Personal Statement for Tech Nation.*', content, re.IGNORECASE)
    title = title_match.group(0) if title_match else "Personal Statement for Tech Nation Global Talent Visa"

    author_match = re.search(r'By (.*?)(?=\n|$)', content)
    author = author_match.group(1) if author_match else ""

    # Add title to HTML
    html_output += f'<h1>{title}</h1>\n'
    if author:
        html_output += f'<p style="text-align: center; font-style: italic;">By {author}</p>\n'

    # Remove title and author from content
    if title_match:
        content = content.replace(title_match.group(0), '')
    if author_match:
        content = content.replace(f"By {author_match.group(1)}", '')

    # Split content by sections (marked with #)
    sections = content.split('#')

    for section in sections:
        if not section.strip():
            continue

        # Remove any -- markers
        section = section.replace('--', '')

        # Process the section
        lines = section.strip().split('\n')
        section_title = lines[0].strip()

        if section_title:
            html_output += f'<h2>{section_title}</h2>\n'

        # Process the rest of the section content
        section_content = '\n'.join(lines[1:]).strip()

        # Process subsections (marked with ##)
        subsections = section_content.split('##')

        for i, subsection in enumerate(subsections):
            if not subsection.strip():
                continue

            subsection_lines = subsection.strip().split('\n')

            # If this is not the first subsection, it has a title
            if i > 0 and subsection_lines[0].strip():
                subsection_title = subsection_lines[0].strip()
                html_output += f'<h3>{subsection_title}</h3>\n'
                subsection_content = '\n'.join(subsection_lines[1:]).strip()
            else:
                subsection_content = subsection.strip()

            # Process paragraphs and lists
            paragraphs = re.split(r'\n\s*\n', subsection_content)

            for para in paragraphs:
                if not para.strip():
                    continue

                # Check if this is a list
                if re.search(r'^\s*-\s+', para.strip(), re.MULTILINE):
                    # This is a list
                    list_items = re.findall(r'^\s*-\s+(.*?)$', para, re.MULTILINE)
                    if list_items:
                        html_output += '<ul style="list-style: disc outside none; margin-left: 20px; margin-bottom: 15px;">\n'
                        for item in list_items:
                            html_output += f'<li style="margin-bottom: 8px;">{item.strip()}</li>\n'
                        html_output += '</ul>\n'
                # Check for checkmarks (✅)
                elif '✅' in para:
                    # This is a list with checkmarks
                    list_items = para.split('✅')
                    if len(list_items) > 1:  # Skip the first empty item
                        html_output += '<ul style="list-style: none; margin-left: 20px; margin-bottom: 15px;">\n'
                        for item in list_items[1:]:
                            if item.strip():
                                html_output += f'<li style="margin-bottom: 8px;">✅ {item.strip()}</li>\n'
                        html_output += '</ul>\n'
                else:
                    # Regular paragraph
                    html_output += f'<p>{para.strip()}</p>\n'

        # Add horizontal rule after each main section
        html_output += '<hr>\n'

    # Process bold text
    html_output = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html_output)

    # Process links
    html_output = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', html_output)

    # Add disclaimer at the bottom
    html_output += """
    <div class="disclaimer-box" style="background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 15px; margin-top: 20px; border-radius: 5px;">
        <h4 style="color: #721c24; margin-top: 0;">📝 Important Notice</h4>
        <p>This document was generated based on the provided CV and instructions. Before submitting:</p>
        <ul style="list-style: disc outside none; margin-left: 20px; margin-bottom: 15px;">
            <li style="margin-bottom: 8px;">Review all content for accuracy</li>
            <li style="margin-bottom: 8px;">Replace any placeholder text</li>
            <li style="margin-bottom: 8px;">Ensure all claims are supported by evidence</li>
            <li style="margin-bottom: 8px;">Verify word count meets requirements (800-1000 words)</li>
            <li style="margin-bottom: 8px;">Customize to reflect your unique achievements and experiences</li>
        </ul>
    </div>
    """

    # Close the personal statement div
    html_output += '</div>'

    return html_output

def generate_document_task(cv_content, instructions, user_id, task_id):
    """Process document generation with fallback"""
    try:
        # Update status to processing
        cache.set(f"task_status_{task_id}", {"status": "processing", "progress": 10}, 3600)

        # Get document ID from cache
        document_id = cache.get(f"task_document_{task_id}")

        # Create the prompt
        prompt = f"""
        Please write a personal statement for a Tech Nation Global Talent Visa application based on the following CV content and instructions.

        The personal statement should:
        1. Be well-structured and professional
        2. Focus on technical achievements and innovations
        3. Highlight leadership and impact
        4. Include specific examples from the CV
        5. Be around 1000 words

        CV Content:
        {cv_content}

        Additional Instructions:
        {instructions}

        Please write the personal statement in first person and ensure it aligns with Tech Nation's criteria.
        Format the statement with clear section headers using # for main sections and ## for subsections.
        Use bullet points with - for lists and bold text with ** for emphasis.
        """

        # Update progress
        cache.set(f"task_status_{task_id}", {"status": "processing", "progress": 30}, 3600)

        # Try DeepSeek first
        raw_content = ai_provider.try_deepseek(prompt)
        provider_used = "DeepSeek"

        # If DeepSeek fails, try OpenAI
        if not raw_content:
            logger.info(f"DeepSeek failed, falling back to OpenAI for task {task_id}")
            raw_content = ai_provider.try_openai(prompt)
            provider_used = "OpenAI"

        # If both providers fail
        if not raw_content:
            raise Exception("Both AI providers failed to generate content")

        # Format the content for the frontend
        formatted_content = process_content_for_frontend(raw_content)

        # Update progress
        cache.set(f"task_status_{task_id}", {"status": "processing", "progress": 90}, 3600)

        # If we have a document ID, update the document directly
        if document_id:
            try:
                document = Document.objects.get(id=document_id)
                document.content = formatted_content
                document.status = 'completed'
                document.notes = f"Generated using {provider_used}"
                document.save()
                logger.info(f"Document {document_id} updated with content from {provider_used}")
            except Exception as e:
                logger.error(f"Error updating document {document_id}: {str(e)}")

        # Store result in cache
        cache_key = f"task_result_{task_id}"
        cache.set(cache_key, formatted_content, 3600)

        # Mark as complete
        cache.set(f"task_status_{task_id}", {
            "status": "complete",
            "progress": 100,
            "provider": provider_used
        }, 3600)

        return formatted_content

    except Exception as e:
        # Update status to failed
        cache.set(f"task_status_{task_id}", {
            "status": "failed",
            "error": str(e)
        }, 3600)
        logger.error(f"Document generation failed: {str(e)}")
        return None

def format_content_for_frontend(content):
    """Format the content to be compatible with the frontend"""
    # Create a properly formatted HTML structure
    formatted_html = f"""
    <div class="personal-statement">
        <h1>Personal Statement for Tech Nation Global Talent Visa</h1>

        {process_sections(content)}

    </div>
    """
    return formatted_html


def extract_table_text(table):
    """Extract text from a table efficiently"""
    rows = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
        if cells:
            rows.append(" | ".join(cells))
    return "\n".join(rows)

def extract_cv_content(cv_file):
    """Extract text content from CV file with caching"""
    # Check if we've already processed this file
    file_hash = hash(cv_file.read())
    cv_file.seek(0)  # Reset file pointer

    if file_hash in document_cache:
        return document_cache[file_hash]

    try:
        # Create a copy of the file in memory
        file_copy = io.BytesIO(cv_file.read())
        cv_file.seek(0)  # Reset file pointer for future use

        if cv_file.name.lower().endswith('.pdf'):
            try:
                # Use a more efficient PDF extraction method
                pdf_reader = PyPDF2.PdfReader(file_copy)
                content = []
                for page in pdf_reader.pages:
                    content.append(page.extract_text())
                extracted_text = '\n'.join(content)
                document_cache[file_hash] = extracted_text
                return extracted_text
            except Exception as e:
                logger.error(f"Error extracting PDF content: {str(e)}")
                raise Exception(f"Error extracting PDF content: {str(e)}")

        elif cv_file.name.lower().endswith(('.doc', '.docx')):
            try:
                doc = DocxDocument(file_copy)
                content = []
                # Extract text from paragraphs
                for para in doc.paragraphs:
                    if para.text.strip():  # Only add non-empty paragraphs
                        content.append(para.text.strip())

                # Extract text from tables
                for table in doc.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            if cell.text.strip():
                                content.append(cell.text.strip())

                extracted_text = '\n'.join(content)
                document_cache[file_hash] = extracted_text
                return extracted_text
            except Exception as e:
                logger.error(f"Error extracting Word document content: {str(e)}")
                raise Exception(f"Error extracting Word document content: {str(e)}")
        else:
            raise Exception("Unsupported file format. Please upload a PDF or Word document.")

    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        raise Exception(f"Error processing file: {str(e)}")

def save_to_docx(content, title, doc_type):
    """Save content to DOCX file with optimized performance"""
    try:
        from docx import Document as DocxDocument  # Changed import
        from docx.shared import Pt, RGBColor, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
        import re
        from datetime import datetime
        import os

        # Start timing
        start_time = time.time()

        doc = DocxDocument()

        # Set document margins efficiently
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)

        # Add main title
        title_paragraph = doc.add_heading(title, level=1)
        title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in title_paragraph.runs:
            run.font.size = Pt(16)
            run.bold = True

        # Add date
        date_paragraph = doc.add_paragraph()
        date_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        date_run = date_paragraph.add_run(f"Generated on: {datetime.now().strftime('%d %B %Y')}")
        date_run.font.size = Pt(10)
        date_run.italic = True

        # Add separator
        doc.add_paragraph("=" * 50).alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Add disclaimer section
        disclaimer_title = doc.add_heading("DISCLAIMER", level=1)
        disclaimer_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in disclaimer_title.runs:
            run.font.color.rgb = RGBColor(255, 0, 0)
            run.font.size = Pt(14)

        # Add disclaimer text
        DISCLAIMER_TEXT = "This document was automatically generated and should be reviewed for accuracy before submission. The content is based on the information provided and does not guarantee visa approval."
        disclaimer_text = doc.add_paragraph(DISCLAIMER_TEXT)
        disclaimer_text.style = 'Intense Quote'
        disclaimer_text.paragraph_format.space_after = Pt(20)

        # Add separator before main content
        doc.add_paragraph("=" * 50).alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Clean up the content more efficiently
        # Use a single regex operation to remove HTML tags
        content = re.sub(r'<[^>]+>', '', content)

        # Clean up markdown and extra spacing
        content = re.sub(r'\*\*(.*?)\*\*', r'\1', content)
        content = re.sub(r'\n\s*\n', '\n\n', content)
        content = content.strip()

        # Split content into sections and process in chunks
        # This is more memory efficient for large documents
        sections = content.split('\n')
        current_section = None

        # Process sections in batches
        batch_size = 20
        for i in range(0, len(sections), batch_size):
            batch = sections[i:i+batch_size]

            for section in batch:
                section = section.strip()
                if not section:
                    continue

                # Check if this is a section header
                if ':' in section and len(section.split(':')[0]) < 50:
                    current_section = section.split(':')[0].strip()
                    # Add section header
                    header = doc.add_heading(section, level=2)
                    header.paragraph_format.space_before = Pt(20)
                    header.paragraph_format.space_after = Pt(12)
                    for run in header.runs:
                        run.font.size = Pt(13)
                        run.bold = True

                # Handle bullet points
                elif section.startswith('•'):
                    p = doc.add_paragraph(style='List Bullet')
                    p.paragraph_format.left_indent = Inches(0.25)
                    p.paragraph_format.space_after = Pt(8)
                    p.paragraph_format.line_spacing = 1.15
                    run = p.add_run(section[1:].strip())
                    run.font.size = Pt(11)

                # Regular paragraphs
                else:
                    p = doc.add_paragraph()
                    p.paragraph_format.space_after = Pt(12)
                    p.paragraph_format.line_spacing = 1.15
                    run = p.add_run(section)
                    run.font.size = Pt(11)

        # Add footer
        footer = doc.sections[0].footer
        footer_paragraph = footer.paragraphs[0]
        footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer_run = footer_paragraph.add_run(
            f"Generated by Tech Nation Visa Assistant • {datetime.now().strftime('%d %B %Y')}"
        )
        footer_run.font.size = Pt(8)
        footer_run.italic = True

        # Create directory if it doesn't exist
        os.makedirs('generated_documents', exist_ok=True)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{doc_type}_{timestamp}.docx"
        filepath = os.path.join('generated_documents', filename)

        # Save the document
        doc.save(filepath)

        # Log performance
        end_time = time.time()
        logger.info(f"DOCX generation took {end_time - start_time:.2f} seconds")

        return filepath

    except Exception as e:
        logger.error(f"Error saving to DOCX: {str(e)}")
        return None

def chunk_cv_content(cv_content, chunk_size=4000, overlap=500):
    """Split CV content into overlapping chunks for better processing"""
    if len(cv_content) <= chunk_size:
        return [cv_content]

    chunks = []
    start = 0
    while start < len(cv_content):
        end = min(start + chunk_size, len(cv_content))
        # If not at the end, try to find a good break point
        if end < len(cv_content):
            # Try to find a newline to break at
            newline_pos = cv_content.rfind('\n', start + chunk_size - overlap, end)
            if newline_pos > start:
                end = newline_pos + 1

        chunks.append(cv_content[start:end])
        start = end - overlap if end < len(cv_content) else end

    return chunks

def create_analysis_prompt(cv_chunk, track, requirements):
    """Create a prompt for analyzing a CV chunk"""
    return f"""
    Please analyze this portion of a CV for a Tech Nation Global Talent Visa application in the {track} track.
    Provide analysis focusing on the following aspects:

    1. Technical expertise and skills
    2. Leadership experience
    3. Innovation contributions
    4. Professional recognition

    CV Content:
    {cv_chunk}

    Requirements for {track}:
    {requirements}
    """

def process_cv_chunk(prompt):
    """Process a single CV chunk with OpenAI"""
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",  # Use faster model for chunks
            messages=[
                {
                    "role": "system",
                    "content": "You are analyzing a portion of a CV for a Tech Nation visa application."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error processing CV chunk: {str(e)}")
        return f"Error: {str(e)}"

def synthesize_chunk_results(chunk_results):
    """Combine and synthesize results from multiple chunks"""
    # Create a prompt to synthesize the results
    synthesis_prompt = f"""
    Synthesize these analyses of different parts of a CV into a single coherent analysis.
    Provide a structured analysis in JSON format with the following sections:

    1. strength_score: A number between 0-100 indicating overall CV strength
    2. summary: A brief overview of the CV's strengths and weaknesses
    3. technical_expertise: List of points about technical skills and suggestions
    4. leadership: List of points about leadership experience and suggestions
    5. innovation: List of points about innovative contributions
    6. recognition: List of points about professional recognition
    7. missing_elements: List of critical missing components
    8. formatting: List of formatting and presentation suggestions

    Format the response as a valid JSON object with these exact keys.

    Individual analyses:
    {' '.join(chunk_results)}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",  # Use more powerful model for synthesis
            messages=[
                {
                    "role": "system",
                    "content": "You are synthesizing multiple analyses of a CV into a single coherent analysis."
                },
                {
                    "role": "user",
                    "content": synthesis_prompt
                }
            ],
            temperature=0.7,
            max_tokens=2000
        )

        analysis_text = response.choices[0].message.content

        # Try to parse JSON from the response
        try:
            # Find JSON content (in case there's additional text)
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if json_match:
                analysis_json = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found in response")

            # Structure the response
            structured_analysis = {
                'strength_score': int(analysis_json.get('strength_score', 70)),
                'summary': analysis_json.get('summary', ''),
                'suggestions': {
                    'technical_expertise': analysis_json.get('technical_expertise', []),
                    'leadership': analysis_json.get('leadership', []),
                    'innovation': analysis_json.get('innovation', []),
                    'recognition': analysis_json.get('recognition', [])
                },
                'missing_elements': analysis_json.get('missing_elements', []),
                'formatting_recommendations': analysis_json.get('formatting', [])
            }

            return structured_analysis

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error in synthesis: {str(e)}")
            return process_text_response(analysis_text)

    except Exception as e:
        logger.error(f"Error in synthesis: {str(e)}")
        return {
            'error': f"Error synthesizing analysis: {str(e)}"
        }

def process_text_response(text):
    """Process plain text response when JSON parsing fails"""
    try:
        # Initialize structure
        analysis = {
            'strength_score': 70,
            'summary': '',
            'suggestions': {
                'technical_expertise': [],
                'leadership': [],
                'innovation': [],
                'recognition': []
            },
            'missing_elements': [],
            'formatting_recommendations': []
        }

        # Extract score if present
        score_match = re.search(r'(\d+)(?:/100|%)', text)
        if score_match:
            analysis['strength_score'] = int(score_match.group(1))

        # Split into sections
        sections = text.split('\n\n')
        current_section = None

        for section in sections:
            section = section.strip()
            if not section:
                continue

            # Process each section
            if 'Technical' in section:
                points = extract_points(section)
                analysis['suggestions']['technical_expertise'] = points
            elif 'Leadership' in section:
                points = extract_points(section)
                analysis['suggestions']['leadership'] = points
            elif 'Innovation' in section:
                points = extract_points(section)
                analysis['suggestions']['innovation'] = points
            elif 'Recognition' in section:
                points = extract_points(section)
                analysis['suggestions']['recognition'] = points
            elif 'Missing' in section:
                points = extract_points(section)
                analysis['missing_elements'] = points
            elif 'Format' in section:
                points = extract_points(section)
                analysis['formatting_recommendations'] = points
            elif 'Summary' in section or 'Overall' in section:
                analysis['summary'] = clean_text(section)

        return analysis

    except Exception as e:
        logger.error(f"Error in text processing: {str(e)}")
        return {
            'error': f"Error processing analysis: {str(e)}"
        }

def extract_points(text):
    """Extract bullet points from text"""
    points = []
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        # Skip headers and empty lines
        if not line or ':' in line and len(line) < 50:
            continue
        # Clean up bullet points
        line = re.sub(r'^[-•*\d]+\.?\s*', '', line)
        if line:
            points.append(line)
    return points

def clean_text(text):
    """Clean up text content"""
    # Remove common headers
    text = re.sub(r'^(Summary|Overall|Analysis):\s*', '', text, flags=re.IGNORECASE)
    return text.strip()

def get_tech_nation_requirements(track):
    """Get requirements based on track with caching"""
    cache_key = f"tech_nation_requirements_{track}"
    cached_requirements = cache.get(cache_key)

    if cached_requirements:
        return cached_requirements

    requirements = {
        'digital_technology': {
            'mandatory': [
                'Technical expertise in building, using, deploying or exploiting technology',
                'Proven innovation contributions or exceptional promise',
                'Recognition as a leading talent in the digital technology sector'
            ],
            'qualifying': [
                'Significant technical or commercial contributions to the sector',
                'Academic contributions through research/teaching/publications',
                'Recognition through awards, speaking engagements, or media coverage',
                'Experience leading or playing a key role in technical projects',
                'Continuous learning and adaptation to new technologies',
                'Contributions to open source projects or tech community'
            ]
        },
        'data_science_ai': {
            'mandatory': [
                'Advanced expertise in AI, machine learning, or data science',
                'Proven track record of innovative AI/data solutions',
                'Recognition in the AI/data science community'
            ],
            'qualifying': [
                'Development of novel AI algorithms or models',
                'Publications in peer-reviewed AI/ML journals or conferences',
                'Contributions to major AI/data science projects',
                'Leadership in AI research or development teams',
                'Patents or intellectual property in AI/ML',
                'Speaking engagements at AI conferences',
                'Collaboration with recognized AI institutions'
            ]
        },
        # Other tracks remain the same...
    }

    # Get the requirements for the specified track or default to digital technology
    track_requirements = requirements.get(track, requirements['digital_technology'])

    # Format the requirements for better presentation
    formatted_requirements = {
        'mandatory': "\n".join(f"• {item}" for item in track_requirements['mandatory']),
        'qualifying': "\n".join(f"• {item}" for item in track_requirements['qualifying'])
    }

    # Cache the formatted requirements for 1 week (these rarely change)
    cache.set(cache_key, formatted_requirements, 60 * 60 * 24 * 7)

    return formatted_requirements

def process_single_document(doc_id, user):
    """Process a single document"""
    try:
        document = Document.objects.get(id=doc_id, user=user)

        # Process based on document type
        if document.document_type == 'cv':
            # Analyze CV
            if document.file:
                with open(document.file.path, 'rb') as f:
                    file_copy = io.BytesIO(f.read())

                cv_content = extract_cv_content(file_copy)

                # Get analysis
                track = 'digital_technology'  # Default track
                requirements = get_tech_nation_requirements(track)

                # Create analysis prompt
                prompt = f"""
                Please analyze this CV for a Tech Nation Global Talent Visa application.
                Provide a brief summary of strengths and weaknesses.

                CV Content:
                {cv_content[:8000]}  # Limit content size

                Requirements:
                {requirements}
                """

                # Call OpenAI
                response = client.chat.completions.create(
                    model="gpt-4.1-nano",
                    messages=[
                        {"role": "system", "content": "You are analyzing a CV for a Tech Nation visa application."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=500
                )

                analysis = response.choices[0].message.content

                # Update document with analysis
                document.notes = analysis
                document.status = 'analyzed'
                document.save()

                return {"status": "success", "analysis": analysis}

        elif document.document_type == 'personal_statement':
            # Generate DOCX version if needed
            if document.content and not document.generated_file:
                filepath = save_to_docx(
                    content=document.content,
                    title=document.title,
                    doc_type="personal_statement"
                )

                if filepath:
                    from django.core.files import File
                    with open(filepath, 'rb') as f:
                        document.generated_file.save(
                            os.path.basename(filepath),
                            File(f),
                            save=True
                        )

                    # Clean up temporary file
                    try:
                        os.remove(filepath)
                    except:
                        pass

                return {"status": "success", "file_generated": True}

        # Default return for other document types
        return {"status": "success", "message": "Document processed"}

    except Document.DoesNotExist:
        return {"status": "error", "message": "Document not found"}
    except Exception as e:
        logger.error(f"Error processing document {doc_id}: {str(e)}")
        return {"status": "error", "message": str(e)}

@login_required
def document_list(request):
    """View all user documents with caching"""
    # Clear cache if requested via query param or after modifications
    if 't' in request.GET:
        cache_key = f"document_list_{request.user.id}"
        cache.delete(cache_key)

    cache_key = f"document_list_{request.user.id}"
    cached_data = cache.get(cache_key)

    if cached_data and 'no_cache' not in request.GET:
        return render(request, 'document_manager/document_list.html', cached_data)

    documents = Document.objects.filter(user=request.user).order_by('document_type', '-updated_at')

    # Group documents by type
    document_groups = {}
    for doc in documents:
        doc_type = doc.get_document_type_display()
        if doc_type not in document_groups:
            document_groups[doc_type] = []
        document_groups[doc_type].append(doc)

    context = {'document_groups': document_groups}
    cache.set(cache_key, context, 60 * 15)  # Cache for 15 minutes

    return render(request, 'document_manager/document_list.html', context)


@login_required
def document_list_partial(request):
    """Partial view for HTMX to load document list"""
    documents = Document.objects.filter(user=request.user).order_by('-updated_at')[:5]
    return render(request, 'document_manager/partials/document_list_partial.html', {
        'documents': documents
    })

@login_required
def document_detail(request, document_id):
    """View and edit a document"""
    document = get_object_or_404(Document, id=document_id, user=request.user)

    if request.method == 'POST':
        if document.document_type == 'personal_statement':
            form = PersonalStatementForm(request.POST, instance=document)
        elif document.document_type == 'cv':
            form = CVForm(request.POST, request.FILES, instance=document)
        else:
            form = DocumentForm(request.POST, request.FILES, instance=document)

        if form.is_valid():
            document = form.save(commit=False)

            # Calculate word count for text content
            if document.content:
                document.word_count = len(document.content.split())

            document.save()

            # Clear cache for document list
            cache.delete(f"document_list_{request.user.id}")

            messages.success(request, f"{document.title} has been updated.")
            return redirect('document_detail', document_id=document.id)
    else:
        if document.document_type == 'personal_statement':
            form = PersonalStatementForm(instance=document)
        elif document.document_type == 'cv':
            form = CVForm(instance=document)
        else:
            form = DocumentForm(instance=document)

    return render(request, 'document_manager/document_detail.html', {
        'document': document,
        'form': form
    })

@login_required
def create_document(request, doc_type):
    """Create a new document"""
    if request.method == 'POST':
        if doc_type == 'personal_statement':
            form = PersonalStatementForm(request.POST)
        elif doc_type == 'cv':
            form = CVForm(request.POST, request.FILES)
        else:
            form = DocumentForm(request.POST, request.FILES)

        if form.is_valid():
            document = form.save(commit=False)
            document.user = request.user
            document.document_type = doc_type
            document.save()

            # Clear cache for document list
            cache.delete(f"document_list_{request.user.id}")

            messages.success(request, f"{document.title} has been created.")
            return redirect('document_detail', document_id=document.id)
    else:
        if doc_type == 'personal_statement':
            form = PersonalStatementForm(initial={'title': 'Personal Statement'})
        elif doc_type == 'cv':
            form = CVForm(initial={'title': 'Curriculum Vitae'})
        else:
            form = DocumentForm()

    return render(request, 'document_manager/create_document.html', {
        'form': form,
        'doc_type': doc_type
    })

@login_required
def personal_statement_builder(request):
    """View for building personal statements"""
    # Add guidelines list
    guidelines = [
        "Your personal statement should demonstrate your exceptional talent and potential in the digital technology sector",
        "Focus on showcasing your technical skills, innovations, and impact in your field",
        "Include specific examples of projects, achievements, and contributions",
        "Highlight any recognition, awards, or publications in your area of expertise",
        "Demonstrate your potential to become a leader in the UK tech sector",
        "Include evidence of how you've contributed to the growth of companies or organizations",
        "Explain how you plan to contribute to the UK's digital technology sector",
        "Keep your statement clear, concise, and well-structured",
        "Ensure all claims are supported by evidence in your CV",
        "Aim for 800-1000 words to comprehensively cover your achievements"
    ]

    doc_generator = GeminiDocumentGenerator()

    # Get user's CVs - use select_related for efficiency
    user_cvs = Document.objects.filter(
        user=request.user,
        document_type='cv'
    ).order_by('-updated_at')

    # Check if user already has a chosen personal statement - use exists() for efficiency
    has_chosen_statement = Document.objects.filter(
        user=request.user,
        document_type='personal_statement',
        is_chosen=True
    ).exists()

    return render(request, 'document_manager/personal_statement_builder.html', {
        'guidelines': guidelines,
        'user_cvs': user_cvs,
        'has_chosen_statement': has_chosen_statement
    })

@login_required
@rate_limit(max_calls=5, window=60)  # Limit to 5 calls per minute
@require_http_methods(["POST"])
def analyze_cv(request):
    """Analyze CV using OpenAI and Tech Nation requirements with caching and rate limiting"""
    try:
        if 'cv_file' not in request.FILES:
            return JsonResponse({'error': 'No CV file uploaded'}, status=400)

        cv_file = request.FILES['cv_file']
        track = request.POST.get('track', 'digital_technology')

        # Generate a unique key for this analysis
        file_hash = hash(cv_file.read())
        cv_file.seek(0)  # Reset file pointer
        cache_key = f"cv_analysis_{file_hash}_{track}"

        # Check cache first
        cached_analysis = cache.get(cache_key)
        if cached_analysis:
            logger.info(f"Using cached CV analysis for user {request.user.id}")
            return JsonResponse(cached_analysis)

        # Extract CV content
        cv_content = extract_cv_content(cv_file)
        if not cv_content:
            return JsonResponse({'error': 'Could not extract content from CV'}, status=400)

        # Get Tech Nation requirements
        requirements = get_tech_nation_requirements(track)

        # Prepare the analysis prompt
        prompt = f"""
        Please analyze this CV for a Tech Nation Global Talent Visa application in the {track} track.
        Provide a structured analysis in JSON format with the following sections:

        1. strength_score: A number between 0-100 indicating overall CV strength
        2. summary: A brief overview of the CV's strengths and weaknesses
        3. technical_expertise: List of points about technical skills and suggestions
        4. leadership: List of points about leadership experience and suggestions
        5. innovation: List of points about innovative contributions
        6. recognition: List of points about professional recognition
        7. missing_elements: List of critical missing components
        8. formatting: List of formatting and presentation suggestions

        Format the response as a valid JSON object with these exact keys.

        CV Content:
        {cv_content}

        Requirements for {track}:
        {requirements}
        """

        # Check if prompt is too long (OpenAI has token limits)
        if len(prompt) > 12000:  # Approximate token limit
            # Truncate CV content to fit within limits
            max_cv_length = 8000  # Leave room for other parts
            cv_content = cv_content[:max_cv_length] + "... [content truncated]"

            # Rebuild prompt with truncated content
            prompt = f"""
            Please analyze this CV for a Tech Nation Global Talent Visa application in the {track} track.
            Provide a structured analysis in JSON format with the following sections:

            1. strength_score: A number between 0-100 indicating overall CV strength
            2. summary: A brief overview of the CV's strengths and weaknesses
            3. technical_expertise: List of points about technical skills and suggestions
            4. leadership: List of points about leadership experience and suggestions
            5. innovation: List of points about innovative contributions
            6. recognition: List of points about professional recognition
            7. missing_elements: List of critical missing components
            8. formatting: List of formatting and presentation suggestions

            Format the response as a valid JSON object with these exact keys.

            CV Content (truncated):
            {cv_content}

            Requirements for {track}:
            {requirements}
            """

        # Call OpenAI API with timing
        start_time = time.time()
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert CV analyst for Tech Nation Global Talent Visa applications. Provide analysis in JSON format."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=2000
        )
        api_time = time.time() - start_time
        logger.info(f"OpenAI API call took {api_time:.2f} seconds for user {request.user.id}")

        # Extract the response
        analysis_text = response.choices[0].message.content

        # Try to parse JSON from the response
        try:
            # Find JSON content (in case there's additional text)
            json_match = re.search(r'\{.*\}', analysis_text, re.DOTALL)
            if json_match:
                analysis_json = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found in response")

            # Structure the response
            structured_analysis = {
                'strength_score': int(analysis_json.get('strength_score', 70)),
                'summary': analysis_json.get('summary', ''),
                'suggestions': {
                    'technical_expertise': analysis_json.get('technical_expertise', []),
                    'leadership': analysis_json.get('leadership', []),
                    'innovation': analysis_json.get('innovation', []),
                    'recognition': analysis_json.get('recognition', [])
                },
                'missing_elements': analysis_json.get('missing_elements', []),
                'formatting_recommendations': analysis_json.get('formatting', [])
            }

            # Cache the result for 24 hours
            cache.set(cache_key, structured_analysis, 60 * 60 * 24)

            return JsonResponse(structured_analysis)

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {str(e)}")
            logger.error(f"Raw response: {analysis_text}")

            # Fallback to text processing if JSON parsing fails
            result = process_text_response(analysis_text)

            # Cache the result for 24 hours
            cache.set(cache_key, result, 60 * 60 * 24)

            return JsonResponse(result)

    except Exception as e:
        logger.error(f"Error in CV analysis: {str(e)}")
        return JsonResponse({
            'error': f"Error analyzing CV: {str(e)}"
        }, status=500)

@login_required
@rate_limit(max_calls=5, window=300)
@require_http_methods(["POST"])
def generate_personal_statement(request):
    """Generate personal statement with background processing"""
    try:
        # Get the uploaded CV file
        cv_file = request.FILES.get('cv')
        if not cv_file:
            return JsonResponse({'success': False, 'error': 'No CV file provided'}, status=400)

        # Validate file size
        if cv_file.size > 10 * 1024 * 1024:  # 10MB limit
            return JsonResponse({'success': False, 'error': 'File size too large. Maximum size is 10MB'}, status=400)

        # Get other form data
        statement_type = request.POST.get('type')
        instructions = request.POST.get('instructions', '')

        # Extract CV content
        try:
            cv_content = extract_cv_content(cv_file)
            if not cv_content:
                return JsonResponse({'success': False, 'error': 'Could not extract content from CV'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Error extracting CV content: {str(e)}'}, status=400)

        # Create title based on statement type
        title_map = {
            'technical': 'Technical Achievement Personal Statement',
            'leadership': 'Leadership & Innovation Personal Statement',
            'research': 'Research & Academic Personal Statement',
            'entrepreneurial': 'Entrepreneurial Personal Statement'
        }
        title = title_map.get(statement_type, 'Tech Nation Personal Statement')

        # Create a document in the database FIRST
        document = Document.objects.create(
            user=request.user,
            title=title,
            content="",  # Will be updated when generation completes
            document_type='personal_statement',
            is_generated=True,
            status='in_progress'  # Set initial status
        )

        # Log document creation
        logger.info(f"Created document {document.id} for user {request.user.id}")

        # Check cache for similar requests
        cache_key = f"personal_statement_{hash(cv_content)}_{statement_type}_{hash(instructions)}"
        cached_content = cache.get(cache_key)

        if cached_content:
            # Use cached content
            generated_content = cached_content
            logger.info(f"Using cached personal statement for user {request.user.id}")

            # Update the document with the cached content
            document.content = generated_content
            document.status = 'completed'
            document.save()

            # Clear document list cache
            cache.delete(f"document_list_{request.user.id}")

            return JsonResponse({
                'success': True,
                'generated_content': generated_content,
                'document_id': document.id
            })
        else:
            # Create prompt based on statement type
            type_prompts = {
                'technical': "Focus on technical achievements, innovations, and impact in the tech sector.",
                'leadership': "Emphasize leadership roles, team management, and organizational impact.",
                'research': "Highlight research contributions, publications, and academic achievements.",
                'entrepreneurial': "Focus on business creation, startup experience, and market impact."
            }

            type_instruction = type_prompts.get(statement_type, "")
            combined_instructions = f"{type_instruction} {instructions}".strip()

            # Generate a task ID
            task_id = str(uuid.uuid4())

            # Store document ID in cache for the task
            cache.set(f"task_document_{task_id}", document.id, 3600)

            # Start background processing
            DocumentProcessor.process_in_background(
                generate_document_task,
                cv_content,
                combined_instructions,
                request.user.id,
                task_id
            )

            # Return task ID for status checking
            return JsonResponse({
                'success': True,
                'task_id': task_id,
                'document_id': document.id,
                'status': 'processing'
            })

    except Exception as e:
        logger.error(f"Error generating personal statement: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def document_generation_status(request, task_id):
    """Check status of document generation task"""
    try:
        status = cache.get(f"task_status_{task_id}")
        if not status:
            return JsonResponse({"status": "unknown"})

        # Get document ID from request or cache
        document_id = request.GET.get('document_id')
        if not document_id:
            # Try to get document ID from cache
            document_id = cache.get(f"task_document_{task_id}")
            if not document_id:
                return JsonResponse({"status": "error", "error": "No document ID found"}, status=400)

        # Verify document exists and belongs to user
        try:
            document = Document.objects.get(id=document_id, user=request.user)
        except Document.DoesNotExist:
            logger.error(f"Document {document_id} not found for user {request.user.id}")
            return JsonResponse({"status": "error", "error": "Document not found"}, status=404)

        # If complete, get the result
        if status.get("status") == "complete":
            result = cache.get(f"task_result_{task_id}")
            if result:
                # Update the document with the generated content
                document.content = result
                document.status = 'completed'
                document.save()

                # Log successful update
                logger.info(f"Document {document_id} updated with generated content")

                # Clear document list cache
                cache.delete(f"document_list_{request.user.id}")

                # Include document ID and content in response
                return JsonResponse({
                    "status": "complete",
                    "document_id": document_id,
                    "content": result,
                    "progress": 100
                })
            else:
                return JsonResponse({
                    "status": "error",
                    "error": "Generation completed but no content found"
                }, status=500)
        elif status.get("status") == "failed":
            # Update document status to failed
            document.status = 'failed'
            document.save()

            return JsonResponse({
                "status": "failed",
                "error": status.get("error", "Unknown error during generation")
            })
        else:
            # Still processing
            return JsonResponse({
                "status": "processing",
                "progress": status.get("progress", 0)
            })

    except Exception as e:
        logger.error(f"Error in document_generation_status: {str(e)}")
        return JsonResponse({"status": "error", "error": str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def download_personal_statement(request):
    """Download personal statement as DOCX"""
    try:
        # Get content from POST data
        content = request.POST.get('content')
        if not content:
            return JsonResponse({'error': 'No content provided'}, status=400)

        # Generate the document
        filepath = save_to_docx(
            content=content,
            title="Personal Statement for Tech Nation Global Talent Visa",
            doc_type="personal_statement"
        )

        if not filepath or not os.path.exists(filepath):
            return JsonResponse({'error': 'Failed to generate document'}, status=500)

        try:
            with open(filepath, 'rb') as doc_file:
                response = HttpResponse(
                    doc_file.read(),
                    content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )
                response['Content-Disposition'] = (
                    'attachment; '
                    f'filename="Personal_Statement_{datetime.now().strftime("%Y%m%d")}.docx"'
                )
                return response
        finally:
            # Clean up the temporary file
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                logger.error(f"Error removing temporary file: {str(e)}")

    except Exception as e:
        logger.error(f"Error in download_personal_statement: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_http_methods(["POST"])
def batch_process_documents(request):
    """Process multiple documents in a single request"""
    try:
        data = json.loads(request.body)
        document_ids = data.get('document_ids', [])

        if not document_ids:
            return JsonResponse({"error": "No documents specified"}, status=400)

        # Process documents in parallel
        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_id = {
                executor.submit(process_single_document, doc_id, request.user): doc_id
                for doc_id in document_ids
            }

            for future in concurrent.futures.as_completed(future_to_id):
                doc_id = future_to_id[future]
                try:
                    results[doc_id] = future.result()
                except Exception as e:
                    results[doc_id] = {"status": "error", "message": str(e)}

        return JsonResponse({"results": results})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Error in batch processing: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)

@login_required
@cache_page(60 * 60)  # Cache for 1 hour
def recommendation_guide(request):
    """View for recommendation letter guidelines with caching"""
    cache_key = "recommendation_guide_data"
    context_data = cache.get(cache_key)

    if not context_data:
        try:
            url = "https://technation-globaltalentvisa-guide.notion.site/#f5f1d8fec3cf4b279b1fdbd0e8ff4a43"
            response = requests.get(url, timeout=5)
            soup = BeautifulSoup(response.text, 'html.parser')
            # Process the scraped data if needed
        except Exception as e:
            logger.error(f"Error scraping Tech Nation website: {e}")
            # Continue with default data

        context_data = {
            'recommender_types': [
                {
                    'title': 'Senior Technical Leaders',
                    'description': 'CTO, Technical Director, Head of Engineering, etc.',
                    'examples': [
                        'Chief Technology Officers (CTO)',
                        'VP of Engineering',
                        'Technical Directors',
                        'Head of Development',
                        'Principal Engineers'
                    ],
                    'why_suitable': 'Can validate technical expertise and leadership capabilities'
                },
                # Other recommender types remain the same...
            ],
            'key_requirements': [
                'Letters must be dated and signed',
                'Should be on official letterhead where possible',
                'Must include recommender\'s contact details',
                'Should explain recommender\'s credentials',
                'Must detail how they know you professionally',
                'Should provide specific examples of your work',
                'Must align with Tech Nation criteria'
            ],
            'letter_components': [
                {
                    'title': 'Introduction',
                    'content': 'Establishes recommender\'s credentials and relationship with applicant'
                },
                # Other letter components remain the same...
            ]
        }

        # Cache the context data for 1 day
        cache.set(cache_key, context_data, 60 * 60 * 24)

    return render(request, 'document_manager/recommendation_guide.html', context_data)

@login_required
@require_http_methods(["POST"])
def delete_document(request, document_id):
    """Delete a document with proper error handling"""
    try:
        document = get_object_or_404(Document, id=document_id, user=request.user)
        document_title = document.title  # Save title before deletion
        document.delete()

        # Clear document list cache
        cache.delete(f"document_list_{request.user.id}")

        logger.info(f"Document '{document_title}' deleted by user {request.user.id}")
        return JsonResponse({'success': True, 'message': 'Document deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting document {document_id}: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
@require_http_methods(["POST"])
def save_personal_statement(request):
    """Save or update a personal statement document"""
    try:
        # Parse JSON data from request body
        data = json.loads(request.body)
        document_id = data.get('document_id')
        title = data.get('title')

        if not document_id:
            return JsonResponse({
                'success': False,
                'error': 'No document ID provided'
            }, status=400)

        if not title:
            return JsonResponse({
                'success': False,
                'error': 'No title provided'
            }, status=400)

        # Get the document
        document = get_object_or_404(Document, id=document_id, user=request.user)

        # Update the document title
        document.title = title
        document.save(update_fields=['title'])  # Only update the title field

        # Clear document list cache
        cache.delete(f"document_list_{request.user.id}")

        return JsonResponse({
            'success': True,
            'message': 'Document saved successfully',
            'document_id': document.id
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)

    except Exception as e:
        logger.error(f"Error in save_personal_statement: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
@require_http_methods(["POST"])
def set_document_as_chosen(request, document_id):
    """Set a document as the chosen one for its type"""
    try:
        logger.info(f"Attempting to set document {document_id} as chosen for user {request.user.id}")

        # Get the document
        try:
            document = Document.objects.get(id=document_id, user=request.user)
            logger.info(f"Found document: {document.id}, title: {document.title}")
        except Document.DoesNotExist:
            logger.error(f"Document {document_id} not found for user {request.user.id}")
            return JsonResponse({
                'success': False,
                'error': 'Document not found'
            }, status=404)

        # Check if it's a personal statement
        if document.document_type != 'personal_statement':
            return JsonResponse({
                'success': False,
                'error': 'Only personal statements can be set as chosen'
            }, status=400)

        # Use a transaction to ensure atomicity
        from django.db import transaction
        with transaction.atomic():
            # First, unmark ALL other personal statements
            Document.objects.filter(
                user=request.user,
                document_type='personal_statement',
                is_chosen=True
            ).exclude(id=document_id).update(is_chosen=False)

            # Then mark this one as chosen
            document.is_chosen = True
            document.status = 'completed'
            document.save(update_fields=['is_chosen', 'status'])

        logger.info(f"Successfully set document {document_id} as chosen")

        # Clear document list cache
        cache.delete(f"document_list_{request.user.id}")

        return JsonResponse({
            'success': True,
            'message': 'Document set as chosen successfully'
        })

    except Exception as e:
        logger.error(f"Error in set_document_as_chosen: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

# Add a new endpoint to verify if a document exists
@login_required
def verify_document(request, document_id):
    """Verify if a document exists and belongs to the current user"""
    try:
        document = Document.objects.get(id=document_id, user=request.user)
        return JsonResponse({
            'exists': True,
            'title': document.title,
            'status': document.status
        })
    except Document.DoesNotExist:
        logger.warning(f"Document verification failed: Document {document_id} not found for user {request.user.id}")
        return JsonResponse({'exists': False, 'error': 'Document not found'})
    except Exception as e:
        logger.error(f"Document verification error: {str(e)}")
        return JsonResponse({'exists': False, 'error': str(e)})

@login_required
def evidence_documents(request):
    """View for managing evidence documents with caching"""
    cache_key = f"evidence_documents_{request.user.id}"
    cached_data = cache.get(cache_key)

    if cached_data:
        return render(request, 'document_manager/evidence.html', cached_data)

    # Get user's documents categorized as evidence
    evidence_docs = Document.objects.filter(
        user=request.user,
        document_type='evidence'
    ).order_by('-updated_at')

    context = {
        'evidence_docs': evidence_docs,
        'criteria_categories': [
            {
                'name': 'Exceptional Talent',
                'criteria': [
                    'Innovation',
                    'Significant Contribution',
                    'Recognition',
                    'Technical Knowledge',
                    'Leadership'
                ]
            },
            {
                'name': 'Exceptional Promise',
                'criteria': [
                    'Innovation Potential',
                    'Contribution Potential',
                    'Recognition Potential',
                    'Technical Knowledge Potential',
                    'Leadership Potential'
                ]
            }
        ]
    }

    # Cache for 15 minutes
    cache.set(cache_key, context, 60 * 15)

    return render(request, 'document_manager/evidence.html', context)

@login_required
def cv_builder(request):
    """View for CV builder page"""
    if request.method == 'POST':
        form = CVForm(request.POST, request.FILES)
        if form.is_valid():
            # Save the CV
            cv = form.save(commit=False)
            cv.user = request.user
            cv.document_type = 'cv'
            cv.save()

            # Clear document list cache
            cache.delete(f"document_list_{request.user.id}")

            # Analyze the CV if requested
            if 'analyze' in request.POST:
                try:
                    # Instead of directly calling analyze_cv, we'll make a proper request
                    # This ensures rate limiting and other middleware are applied
                    from django.http import QueryDict
                    from django.middleware.csrf import get_token

                    # Create a new POST request with the CV file
                    post_data = QueryDict('', mutable=True)
                    post_data.update({
                        'cv_file': cv.file,
                        'track': 'digital_technology',
                        'csrfmiddlewaretoken': get_token(request)
                    })

                    # Call analyze_cv directly with the new request
                    analysis_results = analyze_cv(request)

                    return render(request, 'document_manager/cv_builder.html', {
                        'form': form,
                        'analysis': analysis_results,
                        'cv': cv
                    })
                except Exception as e:
                    logger.error(f"Error analyzing CV: {str(e)}")
                    messages.error(request, f"Error analyzing CV: {str(e)}")

            messages.success(request, "CV uploaded successfully.")
            return redirect('document_detail', document_id=cv.id)
    else:
        form = CVForm()

    return render(request, 'document_manager/cv_builder.html', {
        'form': form
    })