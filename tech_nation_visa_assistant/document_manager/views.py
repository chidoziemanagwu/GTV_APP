# views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, FileResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from datetime import datetime
import json
import os
import io
from docx import Document
import PyPDF2
from .models import Document, EligibilityCriteria
from .forms import DocumentForm, PersonalStatementForm, CVForm
from .services import GeminiDocumentGenerator
from openai import OpenAI
from django.conf import settings
import re
from django.shortcuts import render
from bs4 import BeautifulSoup
import requests
from .utils import calculate_application_progress

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def save_to_docx(self, content, title, doc_type):
    """Save content to DOCX file with better formatting"""
    try:
        from docx import Document
        from docx.shared import Pt, RGBColor, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
        import re
        from datetime import datetime
        import os

        doc = Document()

        # Set document margins
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)

        # Add main title
        title = "Personal Statement for Tech Nation Global Talent Visa"
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
        disclaimer_text = doc.add_paragraph(self.DISCLAIMER_TEXT)
        disclaimer_text.style = 'Intense Quote'
        disclaimer_text.paragraph_format.space_after = Pt(20)

        # Add separator before main content
        doc.add_paragraph("=" * 50).alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Clean up the content
        # Remove HTML tags and classes
        content = re.sub(r'<div.*?>', '', content)
        content = re.sub(r'</div>', '', content)
        content = re.sub(r'<p.*?>', '', content)
        content = re.sub(r'</p>', '\n', content)
        content = re.sub(r'<h[1-6].*?>', '', content)
        content = re.sub(r'</h[1-6]>', '\n', content)
        content = re.sub(r'<ul.*?>', '', content)
        content = re.sub(r'</ul>', '', content)
        content = re.sub(r'<li.*?>', '• ', content)
        content = re.sub(r'</li>', '\n', content)
        content = re.sub(r'<strong>(.*?)</strong>', r'\1', content)

        # Remove any remaining HTML tags
        content = re.sub(r'<[^>]+>', '', content)

        # Clean up markdown and extra spacing
        content = re.sub(r'\*\*(.*?)\*\*', r'\1', content)
        content = re.sub(r'\n\s*\n', '\n\n', content)
        content = content.strip()

        # Split content into sections and add to document
        sections = content.split('\n')
        current_section = None

        for section in sections:
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
        return filepath

    except Exception as e:
        print(f"Error saving to DOCX: {str(e)}")
        return None





@login_required
def document_list(request):
    """View all user documents"""
    documents = Document.objects.filter(user=request.user).order_by('document_type', '-updated_at')

    # Group documents by type
    document_groups = {}
    for doc in documents:
        doc_type = doc.get_document_type_display()
        if doc_type not in document_groups:
            document_groups[doc_type] = []
        document_groups[doc_type].append(doc)

    return render(request, 'document_manager/document_list.html', {
        'document_groups': document_groups
    })

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
            document = form.save()

            # Calculate word count for text content
            if document.content:
                document.word_count = len(document.content.split())
                document.save()

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

    # Get user's CVs
    user_cvs = Document.objects.filter(
        user=request.user,
        document_type='cv'
    ).order_by('-updated_at')

    # Check if user already has a chosen personal statement
    has_chosen_statement = Document.objects.filter(
        user=request.user,
        document_type='personal_statement',
        is_chosen=True
    ).exists()

    if request.method == 'POST':
        if 'generate_personal_statement' in request.POST:
            # Handle AJAX request for generating personal statement
            try:
                cv_file = request.FILES.get('cv')
                statement_type = request.POST.get('type')
                instructions = request.POST.get('instructions', '')
                
                # Process CV file
                cv_content = extract_text_from_file(cv_file)
                
                # Generate content using Gemini
                generated_content = doc_generator.generate_personal_statement(
                    cv_content,
                    statement_type,
                    instructions
                )
                
                if generated_content:
                    # Auto-save the generated personal statement
                    # First, unmark any existing chosen statements
                    Document.objects.filter(
                        user=request.user,
                        document_type='personal_statement',
                        is_chosen=True
                    ).update(is_chosen=False)
                    
                    # Create a default title based on the type
                    title_map = {
                        'technical': 'Technical Achievement Personal Statement',
                        'leadership': 'Leadership & Innovation Personal Statement',
                        'research': 'Research & Academic Personal Statement',
                        'entrepreneurial': 'Entrepreneurial Personal Statement'
                    }
                    
                    title = title_map.get(statement_type, 'Tech Nation Personal Statement')
                    
                    # Save the new document
                    document = Document.objects.create(
                        user=request.user,
                        title=title,
                        document_type='personal_statement',
                        content=generated_content,
                        is_generated=True,
                        is_chosen=True,
                        status='completed'
                    )
                    
                    return JsonResponse({
                        'success': True,
                        'generated_content': generated_content,
                        'document_id': document.id
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'error': 'Failed to generate content'
                    })
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                })
                
        elif 'save_personal_statement' in request.POST:
            # Handle AJAX request for saving/updating personal statement
            try:
                data = json.loads(request.body)
                document_id = data.get('document_id')
                title = data.get('title')
                set_as_chosen = data.get('set_as_chosen', False)
                
                if document_id:
                    # Update existing document
                    document = Document.objects.get(id=document_id, user=request.user)
                    document.title = title
                    
                    # If setting as chosen, unmark others first
                    if set_as_chosen and not document.is_chosen:
                        Document.objects.filter(
                            user=request.user,
                            document_type='personal_statement',
                            is_chosen=True
                        ).update(is_chosen=False)
                        document.is_chosen = True
                        document.status = 'completed'
                    
                    document.save()
                    
                    return JsonResponse({
                        'success': True,
                        'document_id': document.id
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'error': 'No document ID provided'
                    })
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                })

    # For GET requests, just render the form
    return render(request, 'document_manager/personal_statement_builder.html', {
        'guidelines': guidelines,
        'user_cvs': user_cvs,
        'has_chosen_statement': has_chosen_statement
    })







    
@login_required
@require_http_methods(["POST"])
def analyze_cv(request):
    """Analyze CV using OpenAI and Tech Nation requirements"""
    try:
        if 'cv_file' not in request.FILES:
            return JsonResponse({'error': 'No CV file uploaded'}, status=400)

        cv_file = request.FILES['cv_file']
        track = request.POST.get('track', 'digital_technology')

        # Extract CV content
        cv_content = extract_cv_content(cv_file)
        if not cv_content:
            return JsonResponse({'error': 'Could not extract content from CV'}, status=400)

        # Get Tech Nation requirements
        requirements = get_tech_nation_requirements(track)

        # Initialize OpenAI client
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

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

        # Call OpenAI API
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

            return JsonResponse(structured_analysis)

        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {str(e)}")
            print(f"Raw response: {analysis_text}")

            # Fallback to text processing if JSON parsing fails
            return process_text_response(analysis_text)

    except Exception as e:
        print(f"Error in CV analysis: {str(e)}")
        return JsonResponse({
            'error': f"Error analyzing CV: {str(e)}"
        }, status=500)

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

        return JsonResponse(analysis)

    except Exception as e:
        print(f"Error in text processing: {str(e)}")
        return JsonResponse({
            'error': f"Error processing analysis: {str(e)}"
        }, status=500)

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
    """Get requirements based on track"""
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
        'fintech': {
            'mandatory': [
                'Technical expertise in financial technology',
                'Innovation in financial services through technology',
                'Recognition in the fintech sector'
            ],
            'qualifying': [
                'Development of innovative fintech solutions',
                'Contributions to financial inclusion or accessibility',
                'Experience with blockchain, cryptocurrencies, or digital payments',
                'Leadership in fintech projects or teams',
                'Regulatory technology expertise',
                'Recognition through fintech awards or media',
                'Partnerships with major financial institutions'
            ]
        },
        'cyber_security': {
            'mandatory': [
                'Advanced expertise in cybersecurity technologies',
                'Proven track record in securing digital systems',
                'Recognition in the cybersecurity community'
            ],
            'qualifying': [
                'Development of security tools or frameworks',
                'Contributions to vulnerability research',
                'Experience in threat detection and response',
                'Leadership in security teams or projects',
                'Security certifications and qualifications',
                'Speaking at security conferences',
                'Published research in cybersecurity'
            ]
        },
        'gaming': {
            'mandatory': [
                'Technical expertise in game development',
                'Innovation in gaming technology or design',
                'Recognition in the gaming industry'
            ],
            'qualifying': [
                'Development of successful games or gaming platforms',
                'Contributions to gaming engines or tools',
                'Experience with AR/VR/XR technologies',
                'Leadership in game development teams',
                'Gaming industry awards or recognition',
                'Speaking at gaming conferences',
                'Patents or IP in gaming technology'
            ]
        },
        'cloud_computing': {
            'mandatory': [
                'Advanced expertise in cloud technologies',
                'Innovation in cloud solutions or architecture',
                'Recognition in the cloud computing sector'
            ],
            'qualifying': [
                'Development of cloud-native applications',
                'Experience with major cloud platforms',
                'Contributions to cloud infrastructure or tools',
                'Leadership in cloud migration projects',
                'Cloud certifications and qualifications',
                'Speaking engagements on cloud topics',
                'Published articles or whitepapers on cloud computing'
            ]
        },
        'dev_ops': {
            'mandatory': [
                'Expertise in DevOps practices and tools',
                'Innovation in deployment and automation',
                'Recognition in the DevOps community'
            ],
            'qualifying': [
                'Implementation of CI/CD pipelines',
                'Development of automation tools',
                'Experience with containerization and orchestration',
                'Leadership in DevOps transformation',
                'Contributions to DevOps tools or frameworks',
                'Speaking at DevOps conferences',
                'Published content on DevOps practices'
            ]
        },
        'product_management': {
            'mandatory': [
                'Technical expertise in product development',
                'Innovation in product strategy and execution',
                'Recognition as a product leader'
            ],
            'qualifying': [
                'Successful product launches and growth',
                'Experience with agile methodologies',
                'User research and data-driven decisions',
                'Leadership of product teams',
                'Product management certifications',
                'Speaking engagements on product topics',
                'Published articles on product management'
            ]
        },
        'ui_ux': {
            'mandatory': [
                'Technical expertise in UI/UX design',
                'Innovation in user experience solutions',
                'Recognition in the design community'
            ],
            'qualifying': [
                'Development of innovative user interfaces',
                'Contributions to design systems',
                'Experience with user research and testing',
                'Leadership in design teams',
                'Design awards or recognition',
                'Speaking at design conferences',
                'Published work on design principles'
            ]
        }
    }

    # Format the requirements for better presentation
    def format_requirements(req_dict):
        mandatory = "\n".join(f"• {item}" for item in req_dict['mandatory'])
        qualifying = "\n".join(f"• {item}" for item in req_dict['qualifying'])
        return {
            'mandatory': mandatory,
            'qualifying': qualifying
        }

    # Get the requirements for the specified track or default to digital technology
    track_requirements = requirements.get(track, requirements['digital_technology'])
    return format_requirements(track_requirements)



def analyze_with_openai(cv_content, requirements, track):
    """Analyze CV using OpenAI API"""
    try:
        # Prepare the analysis prompt
        prompt = f"""
        Analyze this CV for a Tech Nation Global Talent Visa application in the {track} track.

        CV Content:
        {cv_content}

        Requirements for {track}:
        Mandatory Criteria:
        {requirements['mandatory']}

        Qualifying Criteria:
        {requirements['qualifying']}

        Please provide a detailed analysis including:
        1. Overall assessment (score out of 100)
        2. Strengths and weaknesses
        3. Alignment with Tech Nation criteria
        4. Specific suggestions for improvement
        5. Missing elements that should be added
        6. Format and presentation recommendations

        Format the response as a structured analysis with clear sections.
        """

        # Call OpenAI API with new syntax
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert CV analyst specializing in Tech Nation Global Talent Visa applications. Provide detailed, actionable feedback."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=2000
        )

        # Extract and structure the analysis
        analysis = response.choices[0].message.content

        # Process the analysis into structured sections
        structured_analysis = process_openai_analysis(analysis)

        return structured_analysis

    except Exception as e:
        raise Exception(f"Error in OpenAI analysis: {str(e)}")


def process_openai_analysis(analysis_text):
    """Process the raw OpenAI analysis into structured data"""
    try:
        # Extract the score from the text (assuming it's in format like "85/100" or "85%")
        score_match = re.search(r'(\d+)(?:/100|%)', analysis_text)
        strength_score = int(score_match.group(1)) if score_match else 70

        # Initialize structured data
        structured_analysis = {
            'strength_score': strength_score,
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

        # Split the analysis into sections
        sections = analysis_text.split('\n\n')
        current_section = None

        for section in sections:
            section = section.strip()
            if not section:
                continue

            # Identify sections and their content
            if 'Technical Expertise' in section or 'Technical Skills' in section:
                current_section = 'technical_expertise'
                points = extract_bullet_points(section)
                structured_analysis['suggestions']['technical_expertise'].extend(points)

            elif 'Leadership' in section:
                current_section = 'leadership'
                points = extract_bullet_points(section)
                structured_analysis['suggestions']['leadership'].extend(points)

            elif 'Innovation' in section or 'Impact' in section:
                current_section = 'innovation'
                points = extract_bullet_points(section)
                structured_analysis['suggestions']['innovation'].extend(points)

            elif 'Recognition' in section or 'Achievements' in section:
                current_section = 'recognition'
                points = extract_bullet_points(section)
                structured_analysis['suggestions']['recognition'].extend(points)

            elif 'Missing' in section or 'Gaps' in section:
                points = extract_bullet_points(section)
                structured_analysis['missing_elements'].extend(points)

            elif 'Format' in section or 'Presentation' in section:
                points = extract_bullet_points(section)
                structured_analysis['formatting_recommendations'].extend(points)

            elif 'Summary' in section or 'Overall' in section:
                # Clean up the summary text
                summary = section.replace('Summary:', '').replace('Overall:', '').strip()
                structured_analysis['summary'] = summary

        return structured_analysis

    except Exception as e:
        print(f"Error processing analysis: {str(e)}")
        return {
            'strength_score': 70,
            'summary': 'Error processing detailed analysis.',
            'suggestions': {
                'technical_expertise': ['Unable to process technical expertise analysis.'],
                'leadership': ['Unable to process leadership analysis.'],
                'innovation': ['Unable to process innovation analysis.'],
                'recognition': ['Unable to process recognition analysis.']
            },
            'missing_elements': ['Analysis processing error.'],
            'formatting_recommendations': ['Unable to process formatting recommendations.']
        }

def extract_bullet_points(text):
    """Extract bullet points from text section"""
    points = []
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        # Skip section headers and empty lines
        if not line or ':' in line and len(line) < 50:
            continue
        # Remove bullet points and numbers at start
        line = re.sub(r'^[\d\-\•\*\.\s]+', '', line).strip()
        if line:
            points.append(line)
    return points




def extract_section(text, section_keyword):
    """Extract a section from the analysis text"""
    import re
    pattern = f"{section_keyword}.*?(?=\n\n|$)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if match:
        content = match.group(0)
        # Convert bullet points to list
        points = re.findall(r'[•\-\*]\s*(.*?)(?=(?:[•\-\*]|\n\n|$))', content, re.DOTALL)
        return [point.strip() for point in points if point.strip()]
    return []

def extract_suggestions(text, category):
    """Extract suggestions for a specific category"""
    suggestions = extract_section(text, category)
    return [s for s in suggestions if 'suggest' in s.lower() or 'should' in s.lower() or 'add' in s.lower()]

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

            # Analyze the CV if requested
            if 'analyze' in request.POST:
                try:
                    analysis_results = analyze_cv(request)
                    return render(request, 'document_manager/cv_builder.html', {
                        'form': form,
                        'analysis': analysis_results,
                        'cv': cv
                    })
                except Exception as e:
                    messages.error(request, f"Error analyzing CV: {str(e)}")

            messages.success(request, "CV uploaded successfully.")
            return redirect('document_manager:document_detail', document_id=cv.id)
    else:
        form = CVForm()

    return render(request, 'document_manager/cv_builder.html', {
        'form': form
    })




def get_personal_statement_template(user):
    """Generate a template for personal statement based on user profile"""
    template = (
        "# Personal Statement for Tech Nation Global Talent Visa\n\n"
        "## Introduction\n"
        "[Introduce yourself and your role in the digital technology sector]\n\n"
        "## Why the UK?\n"
        "[Explain why you want to work in the UK and how this aligns with your career]\n\n"
        "## Your Planned Occupation\n"
        "[Describe your planned occupation in the UK and how it relates to digital technology]\n\n"
        "## Your Contribution\n"
        "[Explain how you will contribute to the UK digital technology sector]\n\n"
        "## Conclusion\n"
        "[Summarize your application and restate your commitment to contributing to the UK]"
    )
    return template



@login_required
def evidence_documents(request):
    """View for managing evidence documents"""
    # Get user's documents categorized as evidence
    evidence_docs = Document.objects.filter(
        user=request.user,
        document_type='evidence'  # Changed from doc_type to document_type
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

    return render(request, 'document_manager/evidence.html', context)





@login_required
@require_http_methods(["POST"])
def generate_personal_statement(request):
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

        # Initialize document generator
        doc_generator = GeminiDocumentGenerator()

        # Create prompt based on statement type
        type_prompts = {
            'technical': "Focus on technical achievements, innovations, and impact in the tech sector.",
            'leadership': "Emphasize leadership roles, team management, and organizational impact.",
            'research': "Highlight research contributions, publications, and academic achievements.",
            'entrepreneurial': "Focus on business creation, startup experience, and market impact."
        }

        type_instruction = type_prompts.get(statement_type, "")
        combined_instructions = f"{type_instruction} {instructions}".strip()

        # Generate content
        generated_content = doc_generator.generate_personal_statement(
            cv_content,
            combined_instructions
        )

        if not generated_content:
            return JsonResponse({'success': False, 'error': 'Failed to generate content'}, status=500)

        # Create a default title based on the type
        title_map = {
            'technical': 'Technical Achievement Personal Statement',
            'leadership': 'Leadership & Innovation Personal Statement',
            'research': 'Research & Academic Personal Statement',
            'entrepreneurial': 'Entrepreneurial Personal Statement'
        }
        title = title_map.get(statement_type, 'Tech Nation Personal Statement')

        # If this will be the chosen document, unmark any existing chosen personal statements
        Document.objects.filter(
            user=request.user,
            document_type='personal_statement',
            is_chosen=True
        ).update(is_chosen=False)

        # Save as a document - automatically set as chosen
        document = Document.objects.create(
            user=request.user,
            title=title,
            content=generated_content,
            document_type='personal_statement',
            is_generated=True,
            is_chosen=True,
            status='completed'
        )

        return JsonResponse({
            'success': True,
            'generated_content': generated_content,
            'document_id': document.id
        })

    except Exception as e:
        print(f"Error generating personal statement: {str(e)}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)




@login_required
@require_http_methods(["POST"])
def download_personal_statement(request):
    try:
        # Get content from POST data
        content = request.POST.get('content')
        if not content:
            return JsonResponse({'error': 'No content provided'}, status=400)

        # Create document generator
        doc_generator = GeminiDocumentGenerator()

        # Generate the document
        filepath = doc_generator.save_to_docx(
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
                print(f"Error removing temporary file: {str(e)}")

    except Exception as e:
        print(f"Error in download_personal_statement: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)





def extract_cv_content(cv_file):
    """
    Extract text content from CV file (PDF or DOCX)
    Returns the extracted text content or raises an exception if extraction fails
    """
    try:
        import PyPDF2
        from docx import Document
        import io

        # Create a copy of the file in memory
        file_copy = io.BytesIO(cv_file.read())
        cv_file.seek(0)  # Reset file pointer for future use

        if cv_file.name.lower().endswith('.pdf'):
            try:
                pdf_reader = PyPDF2.PdfReader(file_copy)
                content = []
                for page in pdf_reader.pages:
                    content.append(page.extract_text())
                return '\n'.join(content)
            except Exception as e:
                raise Exception(f"Error extracting PDF content: {str(e)}")

        elif cv_file.name.lower().endswith(('.doc', '.docx')):
            try:
                doc = Document(file_copy)
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

                return '\n'.join(content)
            except Exception as e:
                raise Exception(f"Error extracting Word document content: {str(e)}")
        else:
            raise Exception("Unsupported file format. Please upload a PDF or Word document.")

    except Exception as e:
        raise Exception(f"Error processing file: {str(e)}")




@login_required
def recommendation_guide(request):
    """View for recommendation letter guidelines"""
    return render(request, 'document_manager/recommendation_guide.html')



# views.py
@login_required
@require_http_methods(["POST"])
def delete_document(request, document_id):
    try:
        document = get_object_or_404(Document, id=document_id, user=request.user)
        document.delete()
        return JsonResponse({'success': True, 'message': 'Document deleted successfully'})
    except Exception as e:
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
        document.save()

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
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)



@login_required
@require_http_methods(["POST"])
def set_document_as_chosen(request, document_id):
    try:
        # Get the document
        document = get_object_or_404(Document, id=document_id, user=request.user)

        # Check if it's a personal statement
        if document.document_type != 'personal_statement':
            return JsonResponse({
                'success': False,
                'error': 'Only personal statements can be set as chosen'
            }, status=400)

        # First, unmark ALL other personal statements
        Document.objects.filter(
            user=request.user,
            document_type='personal_statement',
            is_chosen=True
        ).exclude(id=document_id).update(is_chosen=False)

        # Then mark this one as chosen
        document.is_chosen = True
        document.status = 'completed'
        document.save()

        return JsonResponse({
            'success': True,
            'message': 'Document set as chosen successfully'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
    

def recommendation_guide(request):
    try:
        url = "https://technation-globaltalentvisa-guide.notion.site/#f5f1d8fec3cf4b279b1fdbd0e8ff4a43"
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"Error scraping Tech Nation website: {e}")
        pass

    context = {
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
            {
                'title': 'Academic Experts',
                'description': 'Professors, Research Leaders, PhD Supervisors',
                'examples': [
                    'University Professors in relevant fields',
                    'Research Laboratory Directors',
                    'PhD Supervisors',
                    'Department Heads',
                    'Research Institute Leaders'
                ],
                'why_suitable': 'Can attest to research contributions and technical knowledge'
            },
            {
                'title': 'Industry Leaders',
                'description': 'CEOs, Founders, Senior Executives of tech companies',
                'examples': [
                    'Tech Company CEOs',
                    'Startup Founders',
                    'Innovation Directors',
                    'Product Leaders',
                    'Senior Technical Consultants'
                ],
                'why_suitable': 'Can verify industry impact and innovation contributions'
            },
            {
                'title': 'Community Leaders',
                'description': 'Tech Community Organizers, Conference Chairs',
                'examples': [
                    'Tech Conference Organizers',
                    'Tech Community Leaders',
                    'Open Source Project Maintainers',
                    'Tech Meetup Founders',
                    'Industry Association Leaders'
                ],
                'why_suitable': 'Can confirm community contributions and influence'
            }
        ],
        'key_requirements': [
            'Letters must be dated and signed',
            'Should be on official letterhead where possible',
            'Must include recommender\'s contact details',  # Fixed apostrophe
            'Should explain recommender\'s credentials',    # Fixed apostrophe
            'Must detail how they know you professionally',
            'Should provide specific examples of your work',
            'Must align with Tech Nation criteria'
        ],
        'letter_components': [
            {
                'title': 'Introduction',
                'content': 'Establishes recommender\'s credentials and relationship with applicant'  # Fixed apostrophe
            },
            {
                'title': 'Technical Expertise',
                'content': 'Specific examples of technical skills and projects'
            },
            {
                'title': 'Innovation',
                'content': 'Details of innovative contributions and impact'
            },
            {
                'title': 'Recognition',
                'content': 'Awards, achievements, and industry recognition'
            },
            {
                'title': 'Leadership',
                'content': 'Examples of team leadership and project management'
            },
            {
                'title': 'Conclusion',
                'content': 'Strong endorsement for the visa application'
            }
        ]
    }

    return render(request, 'document_manager/recommendation_guide.html', context)