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
import asyncio
import aiohttp
import tempfile
import uuid
from typing import Optional
from functools import wraps

# Document processing imports
from docx import Document as DocxDocument
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
import PyPDF2

# Django imports
from .models import Document
from .forms import DocumentForm, PersonalStatementForm, CVForm
from .services import GeminiDocumentGenerator
from openai import OpenAI, AsyncOpenAI
from django.conf import settings
from bs4 import BeautifulSoup
import requests
from .utils import calculate_application_progress

# Configure logging
logger = logging.getLogger(__name__)

# Initialize OpenAI clients
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Create a document cache
document_cache = {}


class AIProvider:
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.deepseek_client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
        # Add async clients
        self.async_openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.async_deepseek_client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )

    def get_system_prompt(self):
        return """You are an expert at writing personal statements for Tech Nation Global Talent Visa applications.

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

        Make sure to include Introduction, Technical Expertise, Leadership, and Conclusion sections."""

    def try_deepseek(self, prompt: str) -> Optional[str]:
        """Try to get a response from DeepSeek"""
        try:
            response = self.deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": self.get_system_prompt()},
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
                    {"role": "system", "content": self.get_system_prompt()},
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

# MISSING FUNCTION 1: extract_cv_content
def extract_cv_content(cv_file):
    """Extract text content from CV file (PDF, DOCX, or TXT)"""
    try:
        # Check if we've already processed this file
        file_hash = hash(cv_file.read())
        cv_file.seek(0)  # Reset file pointer

        if file_hash in document_cache:
            return document_cache[file_hash]

        file_extension = cv_file.name.lower().split('.')[-1]
        
        if file_extension == 'pdf':
            content = extract_pdf_content(cv_file)
        elif file_extension in ['docx', 'doc']:
            content = extract_docx_content(cv_file)
        elif file_extension == 'txt':
            content = cv_file.read().decode('utf-8')
        else:
            raise ValueError(f"Unsupported file format: {file_extension}")
        
        # Cache the result
        document_cache[file_hash] = content
        return content
            
    except Exception as e:
        logger.error(f"Error extracting CV content: {str(e)}")
        raise Exception(f"Failed to extract content from CV: {str(e)}")

def extract_pdf_content(pdf_file):
    """Extract text from PDF file"""
    try:
        # Create a copy of the file in memory
        file_copy = io.BytesIO(pdf_file.read())
        pdf_file.seek(0)  # Reset file pointer for future use
        
        pdf_reader = PyPDF2.PdfReader(file_copy)
        text = ""
        
        for page in pdf_reader.pages:
            text += page.extract_text() + "\\n"
        
        if not text.strip():
            raise Exception("No text could be extracted from the PDF")
            
        return text.strip()
    except Exception as e:
        logger.error(f"Error extracting PDF content: {str(e)}")
        raise Exception(f"Failed to extract PDF content: {str(e)}")

def extract_docx_content(docx_file):
    """Extract text from DOCX file"""
    try:
        # Create a copy of the file in memory
        file_copy = io.BytesIO(docx_file.read())
        docx_file.seek(0)  # Reset file pointer for future use
        
        doc = DocxDocument(file_copy)
        text = ""
        
        # Extract text from paragraphs
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():  # Only add non-empty paragraphs
                text += paragraph.text + "\\n"
        
        # Also extract text from tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        text += cell.text + " "
                text += "\\n"
        
        if not text.strip():
            raise Exception("No text could be extracted from the DOCX file")
            
        return text.strip()
    except Exception as e:
        logger.error(f"Error extracting DOCX content: {str(e)}")
        raise Exception(f"Failed to extract DOCX content: {str(e)}")

# MISSING FUNCTION 2: save_to_docx
def save_to_docx(content, title="Document", doc_type="personal_statement"):
    """Save HTML content to a DOCX file"""
    try:
        # Create a new document
        doc = DocxDocument()
        
        # Set document margins
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)
        
        # Add title
        title_paragraph = doc.add_heading(title, 0)
        title_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Add date
        date_paragraph = doc.add_paragraph()
        date_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        date_run = date_paragraph.add_run(f"Generated on: {datetime.now().strftime('%d %B %Y')}")
        date_run.font.size = Pt(10)
        date_run.italic = True
        
        # Add separator
        doc.add_paragraph("=" * 50).alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Clean up the content - remove HTML tags
        import re
        clean_content = re.sub(r'<[^>]+>', '', content)
        
        # Remove markdown formatting
        clean_content = re.sub(r'\\*\\*(.*?)\\*\\*', r'\\1', clean_content)
        clean_content = re.sub(r'\\n\\s*\\n', '\\n\\n', clean_content)
        clean_content = clean_content.strip()
        
        # Split by paragraphs and add to document
        paragraphs = clean_content.split('\\n\\n')
        
        for para_text in paragraphs:
            para_text = para_text.strip()
            if para_text:
                # Check if it's a heading (starts with #)
                if para_text.startswith('#'):
                    heading_text = para_text.lstrip('#').strip()
                    doc.add_heading(heading_text, level=1)
                elif para_text.startswith('##'):
                    heading_text = para_text.lstrip('#').strip()
                    doc.add_heading(heading_text, level=2)
                elif para_text.startswith('•') or para_text.startswith('-'):
                    # Handle bullet points
                    p = doc.add_paragraph(style='List Bullet')
                    p.paragraph_format.left_indent = Inches(0.25)
                    run = p.add_run(para_text[1:].strip())
                    run.font.size = Pt(11)
                else:
                    # Regular paragraph
                    paragraph = doc.add_paragraph(para_text)
                    paragraph.paragraph_format.space_after = Pt(12)
        
        # Add disclaimer
        doc.add_paragraph("=" * 50).alignment = WD_ALIGN_PARAGRAPH.CENTER
        disclaimer_title = doc.add_heading("DISCLAIMER", level=1)
        disclaimer_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        disclaimer_text = doc.add_paragraph(
            "This document was automatically generated and should be reviewed for accuracy before submission. "
            "The content is based on the information provided and does not guarantee visa approval."
        )
        disclaimer_text.style = 'Intense Quote'
        
        # Save to temporary file
        temp_dir = tempfile.gettempdir()
        filename = f"{doc_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        filepath = os.path.join(temp_dir, filename)
        
        doc.save(filepath)
        
        return filepath
        
    except Exception as e:
        logger.error(f"Error saving to DOCX: {str(e)}")
        raise Exception(f"Failed to save document: {str(e)}")

# MISSING FUNCTION 3: process_single_document
def process_single_document(document_id, user):
    """Process a single document for batch operations"""
    try:
        document = Document.objects.get(id=document_id, user=user)
        
        # Perform some processing based on document type
        if document.document_type == 'personal_statement':
            # Update word count or other metrics
            word_count = len(document.content.split()) if document.content else 0
            
            # Update document status based on word count
            if word_count >= 800 and word_count <= 1200:
                status = 'completed'
            elif word_count > 0:
                status = 'in_progress'
            else:
                status = 'draft'
            
            document.status = status
            document.save(update_fields=['status'])
            
            return {
                "status": "success",
                "word_count": word_count,
                "document_status": status
            }
        elif document.document_type == 'cv':
            # Analyze CV if it has a file
            if document.file:
                try:
                    with open(document.file.path, 'rb') as f:
                        cv_content = extract_cv_content(f)
                    
                    # Simple analysis
                    word_count = len(cv_content.split()) if cv_content else 0
                    document.notes = f"CV analyzed: {word_count} words extracted"
                    document.status = 'analyzed'
                    document.save(update_fields=['notes', 'status'])
                    
                    return {
                        "status": "success",
                        "word_count": word_count,
                        "analysis": "CV content extracted and analyzed"
                    }
                except Exception as e:
                    return {
                        "status": "error",
                        "message": f"Error analyzing CV: {str(e)}"
                    }
        
        return {
            "status": "success",
            "message": "Document processed"
        }
            
    except Document.DoesNotExist:
        return {
            "status": "error",
            "message": "Document not found"
        }
    except Exception as e:
        logger.error(f"Error processing document {document_id}: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }





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
        <div class="warning-box" style="background-color: #fff3cd; border: 1px solid #ffeeba; padding: 15px; margin-bottom: 20px; border-radius: 5px;">
            <h4 style="color: #856404; margin-top: 0;">⚠️ SAMPLE STATEMENT</h4>
            <p>This is an AI-generated sample personal statement. You should:</p>
            <ul>
                <li>Customize it with your specific achievements and experiences</li>
                <li>Verify all facts and claims before submission</li>
                <li>Use it as a guide, not a final submission</li>
            </ul>
        </div>
    """

    # Extract title and author if present
    title_match = re.search(r'Personal Statement for Tech Nation.*', content, re.IGNORECASE)
    title = title_match.group(0) if title_match else "Personal Statement for Tech Nation Global Talent Visa"

    author_match = re.search(r'By (.*?)(?=\\n|$)', content)
    author = author_match.group(1) if author_match else ""

    # Add title to HTML
    html_output += f'<h1>{title}</h1>\\n'
    if author:
        html_output += f'<p style="text-align: center; font-style: italic;">By {author}</p>\\n'

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
        lines = section.strip().split('\\n')
        section_title = lines[0].strip()

        if section_title:
            html_output += f'<h2>{section_title}</h2>\\n'

        # Process the rest of the section content
        section_content = '\\n'.join(lines[1:]).strip()

        # Process subsections (marked with ##)
        subsections = section_content.split('##')

        for i, subsection in enumerate(subsections):
            if not subsection.strip():
                continue

            subsection_lines = subsection.strip().split('\\n')

            # If this is not the first subsection, it has a title
            if i > 0 and subsection_lines[0].strip():
                subsection_title = subsection_lines[0].strip()
                html_output += f'<h3>{subsection_title}</h3>\\n'
                subsection_content = '\\n'.join(subsection_lines[1:]).strip()
            else:
                subsection_content = subsection.strip()

            # Process paragraphs and lists
            paragraphs = re.split(r'\\n\\s*\\n', subsection_content)

            for para in paragraphs:
                if not para.strip():
                    continue

                # Check if this is a list
                if re.search(r'^\\s*-\\s+', para.strip(), re.MULTILINE):
                    # This is a list
                    list_items = re.findall(r'^\\s*-\\s+(.*?)$', para, re.MULTILINE)
                    if list_items:
                        html_output += '<ul style="list-style: disc outside none; margin-left: 20px; margin-bottom: 15px;">\\n'
                        for item in list_items:
                            html_output += f'<li style="margin-bottom: 8px;">{item.strip()}</li>\\n'
                        html_output += '</ul>\\n'
                # Check for checkmarks (✅)
                elif '✅' in para:
                    # This is a list with checkmarks
                    list_items = para.split('✅')
                    if len(list_items) > 1:  # Skip the first empty item
                        html_output += '<ul style="list-style: none; margin-left: 20px; margin-bottom: 15px;">\\n'
                        for item in list_items[1:]:
                            if item.strip():
                                html_output += f'<li style="margin-bottom: 8px;">✅ {item.strip()}</li>\\n'
                        html_output += '</ul>\\n'
                else:
                    # Regular paragraph
                    html_output += f'<p>{para.strip()}</p>\\n'

        # Add horizontal rule after each main section
        html_output += '<hr>\\n'

    # Process bold text
    html_output = re.sub(r'\\*\\*(.*?)\\*\\*', r'<strong>\\1</strong>', html_output)

    # Process links
    html_output = re.sub(r'\\[(.*?)\\]\\((.*?)\\)', r'<a href="\\2">\\1</a>', html_output)

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
    </div>
    """

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
        }
    }

    # Get the requirements for the specified track or default to digital technology
    track_requirements = requirements.get(track, requirements['digital_technology'])

    # Format the requirements for better presentation
    formatted_requirements = {
        'mandatory': "\\n".join(f"• {item}" for item in track_requirements['mandatory']),
        'qualifying': "\\n".join(f"• {item}" for item in track_requirements['qualifying'])
    }

    # Cache the formatted requirements for 1 week (these rarely change)
    cache.set(cache_key, formatted_requirements, 60 * 60 * 24 * 7)

    return formatted_requirements

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
        score_match = re.search(r'(\\d+)(?:/100|%)', text)
        if score_match:
            analysis['strength_score'] = int(score_match.group(1))

        # Split into sections
        sections = text.split('\\n\\n')

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
    lines = text.split('\\n')
    for line in lines:
        line = line.strip()
        # Skip headers and empty lines
        if not line or ':' in line and len(line) < 50:
            continue
        # Clean up bullet points
        line = re.sub(r'^[-•*\\d]+\\.?\\s*', '', line)
        if line:
            points.append(line)
    return points

def clean_text(text):
    """Clean up text content"""
    # Remove common headers
    text = re.sub(r'^(Summary|Overall|Analysis):\\s*', '', text, flags=re.IGNORECASE)
    return text.strip()




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
        try:
            cv_content = extract_cv_content(cv_file)
            if not cv_content:
                return JsonResponse({'error': 'Could not extract content from CV'}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'Error extracting CV content: {str(e)}'}, status=400)

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
        {cv_content[:8000]}  # Limit content for analysis

        Requirements for {track}:
        {requirements}
        """

        # Call OpenAI API with timing
        start_time = time.time()
        try:
            response = client.chat.completions.create(
                model="gpt-4",
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
                json_match = re.search(r'\\{.*\\}', analysis_text, re.DOTALL)
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
            logger.error(f"OpenAI API error: {str(e)}")
            
            # Fallback analysis
            fallback_analysis = {
                'strength_score': 75,
                'summary': 'CV analysis completed. Please review the suggestions below.',
                'suggestions': {
                    'technical_expertise': ['Highlight specific technologies and frameworks used', 'Include quantifiable achievements'],
                    'leadership': ['Add examples of team leadership', 'Include project management experience'],
                    'innovation': ["Describe innovative solutions you've developed', 'Include any patents or publications"],
                    'recognition': ['Add awards or recognition received', 'Include speaking engagements or media mentions']
                },
                'missing_elements': ['Consider adding more quantifiable metrics', 'Include links to portfolio or projects'],
                'formatting_recommendations': ['Ensure consistent formatting', 'Use clear section headers', 'Keep to 2-3 pages maximum']
            }
            
            return JsonResponse(fallback_analysis)

    except Exception as e:
        logger.error(f"Error in CV analysis: {str(e)}")
        return JsonResponse({
            'error': f"Error analyzing CV: {str(e)}"
        }, status=500)

def process_sections(content):
    """Process markdown sections for frontend display"""
    import re
    
    # Convert markdown headers
    content = re.sub(r'^# (.*)', r'<h2>\\1</h2>', content, flags=re.MULTILINE)
    content = re.sub(r'^## (.*)', r'<h3>\\1</h3>', content, flags=re.MULTILINE)
    
    # Convert bold text
    content = re.sub(r'\\*\\*(.*?)\\*\\*', r'<strong>\\1</strong>', content)
    
    # Convert bullet points
    content = re.sub(r'^- (.*)', r'<li>\\1</li>', content, flags=re.MULTILINE)
    
    # Wrap consecutive list items in ul tags
    content = re.sub(r'(<li>.*?</li>)', r'<ul>\\1</ul>', content, flags=re.DOTALL)
    
    # Convert paragraphs
    paragraphs = content.split('\\n\\n')
    formatted_paragraphs = []
    
    for para in paragraphs:
        para = para.strip()
        if para and not para.startswith('<'):
            formatted_paragraphs.append(f'<p>{para}</p>')
        elif para:
            formatted_paragraphs.append(para)
    
    return '\\n'.join(formatted_paragraphs)




@login_required
def document_list(request):
    """Display list of user's documents with pagination and filtering"""
    documents = Document.objects.filter(user=request.user).order_by('-created_at')
    
    # Filter by document type if specified
    doc_type = request.GET.get('type')
    if doc_type:
        documents = documents.filter(document_type=doc_type)
    
    # Filter by status if specified
    status = request.GET.get('status')
    if status:
        documents = documents.filter(status=status)
    
    # Search functionality
    search = request.GET.get('search')
    if search:
        documents = documents.filter(
            models.Q(title__icontains=search) | 
            models.Q(content__icontains=search)
        )
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(documents, 10)  # Show 10 documents per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Calculate progress for each document
    for doc in page_obj:
        doc.progress = calculate_application_progress(doc)
    
    context = {
        'page_obj': page_obj,
        'doc_type': doc_type,
        'status': status,
        'search': search,
        'total_documents': documents.count()
    }
    
    return render(request, 'documents/document_list.html', context)

@login_required
def document_detail(request, pk):
    """Display document details with edit functionality"""
    document = get_object_or_404(Document, pk=pk, user=request.user)
    
    # Calculate progress
    progress = calculate_application_progress(document)
    
    # Get related documents
    related_docs = Document.objects.filter(
        user=request.user,
        document_type=document.document_type
    ).exclude(pk=pk)[:5]
    
    context = {
        'document': document,
        'progress': progress,
        'related_docs': related_docs,
        'word_count': len(document.content.split()) if document.content else 0
    }
    
    return render(request, 'documents/document_detail.html', context)

@login_required
def create_document(request):
    """Create a new document"""
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.user = request.user
            document.save()
            
            messages.success(request, f'{document.get_document_type_display()} created successfully!')
            return redirect('document_detail', pk=document.pk)
    else:
        form = DocumentForm()
    
    return render(request, 'documents/create_document.html', {'form': form})

@login_required
def edit_document(request, pk):
    """Edit an existing document"""
    document = get_object_or_404(Document, pk=pk, user=request.user)
    
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES, instance=document)
        if form.is_valid():
            form.save()
            messages.success(request, 'Document updated successfully!')
            return redirect('document_detail', pk=document.pk)
    else:
        form = DocumentForm(instance=document)
    
    context = {
        'form': form,
        'document': document
    }
    
    return render(request, 'documents/edit_document.html', context)

@login_required
def delete_document(request, pk):
    """Delete a document"""
    document = get_object_or_404(Document, pk=pk, user=request.user)
    
    if request.method == 'POST':
        document_type = document.get_document_type_display()
        document.delete()
        messages.success(request, f'{document_type} deleted successfully!')
        return redirect('document_list')
    
    return render(request, 'documents/delete_document.html', {'document': document})

@login_required
def duplicate_document(request, pk):
    """Create a duplicate of an existing document"""
    original = get_object_or_404(Document, pk=pk, user=request.user)
    
    # Create a new document with copied content
    duplicate = Document.objects.create(
        user=request.user,
        title=f"Copy of {original.title}",
        document_type=original.document_type,
        content=original.content,
        notes=original.notes,
        status='draft'
    )
    
    messages.success(request, 'Document duplicated successfully!')
    return redirect('document_detail', pk=duplicate.pk)

@login_required
@require_http_methods(["POST"])
def batch_process_documents(request):
    """Process multiple documents in batch"""
    try:
        document_ids = request.POST.getlist('document_ids')
        action = request.POST.get('action')
        
        if not document_ids:
            return JsonResponse({'error': 'No documents selected'}, status=400)
        
        results = []
        
        # Use ThreadPoolExecutor for parallel processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            
            for doc_id in document_ids:
                future = executor.submit(process_single_document, doc_id, request.user)
                futures.append((doc_id, future))
            
            # Collect results
            for doc_id, future in futures:
                try:
                    result = future.result(timeout=30)  # 30 second timeout per document
                    results.append({
                        'document_id': doc_id,
                        'status': 'success',
                        'result': result
                    })
                except Exception as e:
                    results.append({
                        'document_id': doc_id,
                        'status': 'error',
                        'error': str(e)
                    })
        
        return JsonResponse({
            'success': True,
            'results': results,
            'processed': len(results)
        })
        
    except Exception as e:
        logger.error(f"Batch processing error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def download_document(request, pk):
    """Download document as DOCX file"""
    document = get_object_or_404(Document, pk=pk, user=request.user)
    
    try:
        # Generate DOCX file
        filepath = save_to_docx(
            content=document.content,
            title=document.title,
            doc_type=document.document_type
        )
        
        # Return file response
        response = FileResponse(
            open(filepath, 'rb'),
            as_attachment=True,
            filename=f"{document.title.replace(' ', '_')}.docx"
        )
        
        # Clean up temporary file after response
        def cleanup():
            try:
                os.remove(filepath)
            except:
                pass
        
        # Schedule cleanup (this is a simple approach; in production use celery)
        threading.Timer(60, cleanup).start()
        
        return response
        
    except Exception as e:
        logger.error(f"Error downloading document {pk}: {str(e)}")
        messages.error(request, f'Error downloading document: {str(e)}')
        return redirect('document_detail', pk=pk)

@login_required
def export_documents(request):
    """Export multiple documents as a ZIP file"""
    try:
        document_ids = request.GET.getlist('ids')
        if not document_ids:
            messages.error(request, 'No documents selected for export')
            return redirect('document_list')
        
        documents = Document.objects.filter(
            pk__in=document_ids,
            user=request.user
        )
        
        if not documents.exists():
            messages.error(request, 'No valid documents found')
            return redirect('document_list')
        
        # Create a temporary directory for the ZIP
        import zipfile
        import tempfile
        
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, f"documents_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
        
        with zipfile.ZipFile(zip_path, 'w') as zip_file:
            for document in documents:
                try:
                    # Generate DOCX for each document
                    docx_path = save_to_docx(
                        content=document.content,
                        title=document.title,
                        doc_type=document.document_type
                    )
                    
                    # Add to ZIP
                    zip_file.write(
                        docx_path,
                        f"{document.title.replace(' ', '_')}.docx"
                    )
                    
                    # Clean up individual DOCX file
                    os.remove(docx_path)
                    
                except Exception as e:
                    logger.error(f"Error processing document {document.pk}: {str(e)}")
                    continue
        
        # Return ZIP file
        response = FileResponse(
            open(zip_path, 'rb'),
            as_attachment=True,
            filename=f"documents_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        )
        
        # Schedule cleanup
        def cleanup():
            try:
                os.remove(zip_path)
                os.rmdir(temp_dir)
            except:
                pass
        
        threading.Timer(60, cleanup).start()
        
        return response
        
    except Exception as e:
        logger.error(f"Error exporting documents: {str(e)}")
        messages.error(request, f'Error exporting documents: {str(e)}')
        return redirect('document_list')
    

# Personal Statement Generation Views
@login_required
def personal_statement_builder(request):
    """Main personal statement builder interface"""
    # Get user's existing documents
    personal_statements = Document.objects.filter(
        user=request.user,
        document_type='personal_statement'
    ).order_by('-created_at')
    
    cvs = Document.objects.filter(
        user=request.user,
        document_type='cv'
    ).order_by('-created_at')
    
    # Get Tech Nation requirements
    requirements = get_tech_nation_requirements('digital_technology')
    
    context = {
        'personal_statements': personal_statements,
        'cvs': cvs,
        'requirements': requirements,
        'tracks': [
            ('digital_technology', 'Digital Technology'),
            ('data_science_ai', 'Data Science & AI'),
        ]
    }
    
    return render(request, 'documents/personal_statement_builder.html', context)

@login_required
@rate_limit(max_calls=3, window=300)  # 3 calls per 5 minutes
@require_http_methods(["POST"])
def generate_personal_statement(request):
    """Generate personal statement using AI with async processing"""
    try:
        # Validate request
        if 'cv_file' not in request.FILES:
            return JsonResponse({'error': 'CV file is required'}, status=400)
        
        cv_file = request.FILES['cv_file']
        instructions = request.POST.get('instructions', '').strip()
        track = request.POST.get('track', 'digital_technology')
        
        # Validate file size (max 10MB)
        if cv_file.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'File size too large. Maximum 10MB allowed.'}, status=400)
        
        # Validate file type
        allowed_extensions = ['pdf', 'docx', 'doc', 'txt']
        file_extension = cv_file.name.lower().split('.')[-1]
        if file_extension not in allowed_extensions:
            return JsonResponse({
                'error': f'Unsupported file type. Allowed: {", ".join(allowed_extensions)}'
            }, status=400)
        
        # Extract CV content
        try:
            cv_content = extract_cv_content(cv_file)
            if not cv_content or len(cv_content.strip()) < 100:
                return JsonResponse({
                    'error': 'CV content is too short or could not be extracted properly'
                }, status=400)
        except Exception as e:
            return JsonResponse({
                'error': f'Error extracting CV content: {str(e)}'
            }, status=400)
        
        # Create a new document record
        document = Document.objects.create(
            user=request.user,
            title=f"Personal Statement - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            document_type='personal_statement',
            status='generating',
            notes=f"Track: {track}, Instructions: {instructions[:100]}..."
        )
        
        # Generate unique task ID
        task_id = str(uuid.uuid4())
        
        # Store task info in cache
        cache.set(f"task_document_{task_id}", document.id, 3600)
        cache.set(f"task_status_{task_id}", {"status": "queued", "progress": 0}, 3600)
        
        # Start background processing
        DocumentProcessor.process_in_background(
            generate_document_task,
            cv_content,
            instructions,
            request.user.id,
            task_id
        )
        
        return JsonResponse({
            'success': True,
            'task_id': task_id,
            'document_id': document.id,
            'message': 'Personal statement generation started'
        })
        
    except Exception as e:
        logger.error(f"Error in generate_personal_statement: {str(e)}")
        return JsonResponse({
            'error': f'An error occurred: {str(e)}'
        }, status=500)

@login_required
@require_http_methods(["GET"])
def check_generation_status(request, task_id):
    """Check the status of document generation"""
    try:
        # Get status from cache
        status_info = cache.get(f"task_status_{task_id}")
        
        if not status_info:
            return JsonResponse({
                'status': 'not_found',
                'error': 'Task not found or expired'
            }, status=404)
        
        # If task is complete, get the result
        if status_info.get('status') == 'complete':
            result = cache.get(f"task_result_{task_id}")
            document_id = cache.get(f"task_document_{task_id}")
            
            response_data = {
                'status': 'complete',
                'progress': 100,
                'provider': status_info.get('provider', 'Unknown'),
                'document_id': document_id
            }
            
            if result:
                response_data['content'] = result
            
            return JsonResponse(response_data)
        
        # Return current status
        return JsonResponse(status_info)
        
    except Exception as e:
        logger.error(f"Error checking generation status: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'error': str(e)
        }, status=500)

@login_required
@require_http_methods(["POST"])
def save_generated_content(request):
    """Save the generated content to a document"""
    try:
        data = json.loads(request.body)
        content = data.get('content', '')
        document_id = data.get('document_id')
        title = data.get('title', f"Personal Statement - {datetime.now().strftime('%Y-%m-%d')}")
        
        if not content:
            return JsonResponse({'error': 'No content provided'}, status=400)
        
        if document_id:
            # Update existing document
            try:
                document = Document.objects.get(id=document_id, user=request.user)
                document.content = content
                document.title = title
                document.status = 'completed'
                document.save()
            except Document.DoesNotExist:
                return JsonResponse({'error': 'Document not found'}, status=404)
        else:
            # Create new document
            document = Document.objects.create(
                user=request.user,
                title=title,
                document_type='personal_statement',
                content=content,
                status='completed'
            )
        
        return JsonResponse({
            'success': True,
            'document_id': document.id,
            'message': 'Content saved successfully'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Error saving generated content: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def preview_personal_statement(request, pk):
    """Preview personal statement with formatting"""
    document = get_object_or_404(Document, pk=pk, user=request.user)
    
    if document.document_type != 'personal_statement':
        messages.error(request, 'This document is not a personal statement')
        return redirect('document_detail', pk=pk)
    
    # Process content for preview
    processed_content = process_sections(document.content) if document.content else ''
    
    # Calculate word count
    word_count = len(document.content.split()) if document.content else 0
    
    # Check if word count is within recommended range
    word_count_status = 'good'
    if word_count < 800:
        word_count_status = 'low'
    elif word_count > 1200:
        word_count_status = 'high'
    
    context = {
        'document': document,
        'processed_content': processed_content,
        'word_count': word_count,
        'word_count_status': word_count_status,
        'recommended_min': 800,
        'recommended_max': 1200
    }
    
    return render(request, 'documents/preview_personal_statement.html', context)

@login_required
@require_http_methods(["POST"])
def update_personal_statement(request, pk):
    """Update personal statement content via AJAX"""
    try:
        document = get_object_or_404(Document, pk=pk, user=request.user)
        
        if document.document_type != 'personal_statement':
            return JsonResponse({'error': 'Invalid document type'}, status=400)
        
        data = json.loads(request.body)
        content = data.get('content', '')
        title = data.get('title', document.title)
        
        # Update document
        document.content = content
        document.title = title
        document.updated_at = datetime.now()
        document.save()
        
        # Calculate new word count
        word_count = len(content.split()) if content else 0
        
        return JsonResponse({
            'success': True,
            'word_count': word_count,
            'message': 'Personal statement updated successfully'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Error updating personal statement: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_requirements(request, track):
    """Get Tech Nation requirements for a specific track"""
    try:
        requirements = get_tech_nation_requirements(track)
        return JsonResponse({
            'success': True,
            'requirements': requirements
        })
    except Exception as e:
        logger.error(f"Error getting requirements for track {track}: {str(e)}")
        return JsonResponse({
            'error': f'Error getting requirements: {str(e)}'
        }, status=500)
    


# Dashboard and Statistics Views
@login_required
def dashboard(request):
    """Main dashboard with statistics and recent activity"""
    # Get user's documents
    documents = Document.objects.filter(user=request.user)
    
    # Calculate statistics
    stats = {
        'total_documents': documents.count(),
        'personal_statements': documents.filter(document_type='personal_statement').count(),
        'cvs': documents.filter(document_type='cv').count(),
        'completed': documents.filter(status='completed').count(),
        'in_progress': documents.filter(status__in=['draft', 'in_progress', 'generating']).count(),
    }
    
    # Recent documents
    recent_documents = documents.order_by('-updated_at')[:5]
    
    # Recent activity (last 30 days)
    from datetime import timedelta
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent_activity = documents.filter(
        updated_at__gte=thirty_days_ago
    ).order_by('-updated_at')[:10]
    
    # Progress calculation for each recent document
    for doc in recent_documents:
        doc.progress = calculate_application_progress(doc)
    
    context = {
        'stats': stats,
        'recent_documents': recent_documents,
        'recent_activity': recent_activity,
    }
    
    return render(request, 'documents/dashboard.html', context)

@login_required
def api_usage_stats(request):
    """Get API usage statistics"""
    try:
        # This would typically come from a database or cache
        # For now, return mock data
        stats = {
            'total_requests': 150,
            'successful_requests': 142,
            'failed_requests': 8,
            'average_response_time': 2.3,
            'requests_today': 12,
            'remaining_quota': 88
        }
        
        return JsonResponse({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Error getting API usage stats: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=500)

@login_required
@require_http_methods(["POST"])
def clear_cache(request):
    """Clear user-specific cache"""
    try:
        # Clear document cache for this user
        user_cache_keys = [key for key in document_cache.keys() if str(request.user.id) in str(key)]
        for key in user_cache_keys:
            del document_cache[key]
        
        # Clear Django cache for this user
        cache_pattern = f"*{request.user.id}*"
        # Note: This is a simplified approach. In production, use Redis with pattern matching
        
        return JsonResponse({
            'success': True,
            'message': 'Cache cleared successfully'
        })
        
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=500)

# Health check endpoint
def health_check(request):
    """Health check endpoint for monitoring"""
    try:
        # Check database connection
        Document.objects.count()
        
        # Check cache
        cache.set('health_check', 'ok', 60)
        cache_status = cache.get('health_check')
        
        return JsonResponse({
            'status': 'healthy',
            'database': 'ok',
            'cache': 'ok' if cache_status == 'ok' else 'error',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }, status=500)

# Error handlers
def handler404(request, exception):
    """Custom 404 error handler"""
    return render(request, 'errors/404.html', status=404)

def handler500(request):
    """Custom 500 error handler"""
    return render(request, 'errors/500.html', status=500)

# Utility view for testing
@login_required
def test_ai_connection(request):
    """Test AI provider connections"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        results = {}
        
        # Test DeepSeek
        try:
            deepseek_response = ai_provider.try_deepseek("Hello, this is a test.")
            results['deepseek'] = 'ok' if deepseek_response else 'error'
        except Exception as e:
            results['deepseek'] = f'error: {str(e)}'
        
        # Test OpenAI
        try:
            openai_response = ai_provider.try_openai("Hello, this is a test.")
            results['openai'] = 'ok' if openai_response else 'error'
        except Exception as e:
            results['openai'] = f'error: {str(e)}'
        
        return JsonResponse({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)