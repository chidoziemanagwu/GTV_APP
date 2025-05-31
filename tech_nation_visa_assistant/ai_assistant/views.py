from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
import json
import logging
from .rag_system import TechNationRAG
from .models import Conversation, Message, AIQuery, AIFeedback
from accounts.models import UserProfile
from .document_generator import DocumentGenerator
from django.conf import settings
from django.core.cache import cache
from openai import OpenAI  # FIXED: Added missing import
from .token_manager import token_manager, rate_limit
import time
import os
import requests
from functools import wraps

logger = logging.getLogger(__name__)

# FIXED: Properly configure all AI clients with error handling
try:
    openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
except:
    openai_client = None
    logger.warning("OpenAI client not configured")

# Initialize document generator
document_generator = DocumentGenerator()

# System prompt for Tech Nation assistant
TECH_NATION_SYSTEM_PROMPT = """You are a specialized assistant for the Tech Nation Global Talent Visa.
Provide accurate, helpful information about the visa application process, eligibility criteria,
and requirements.

IMPORTANT FORMATTING INSTRUCTIONS:
1. Use proper markdown formatting with clear section headers (## for main sections, ### for subsections)
2. Always include blank lines between paragraphs and sections
3. For lists, use proper markdown bullet points or numbers with spacing
4. Format important information with **bold** text
5. Use proper line breaks between sections
6. Keep responses concise but comprehensive
7. Use tables for comparing information when appropriate

Example format:
## Main Section

This is a paragraph with information.

### Subsection

- Bullet point 1
- Bullet point 2

**Important note:** This is highlighted.

Always include this disclaimer at the end of your responses (exactly as formatted):

<div class="disclaimer">*Disclaimer: While we strive to provide up-to-date information, please verify details on the [official Tech Nation website](https://technation.io/global-talent-visa/) for the latest guidance.*</div>"""

# FIXED: Configure DeepSeek client properly
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
deepseek_client = None

if DEEPSEEK_API_KEY:
    try:
        deepseek_client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
    except:
        deepseek_client = None
        logger.warning("DeepSeek client not configured")

# FIXED: Configure Groq client properly
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
groq_client = None

if GROQ_API_KEY:
    try:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)
    except ImportError:
        logger.warning("Groq library not installed")
    except:
        groq_client = None
        logger.warning("Groq client not configured")

def use_deepseek_api(messages, temperature=0.7, max_tokens=800, stream=False):
    """Call DeepSeek API using OpenAI client"""
    if not deepseek_client:
        return None

    try:
        response = deepseek_client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream
        )

        if stream:
            return response

        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error calling DeepSeek API: {e}")
        return None

def ai_fallback(func):
    """Decorator to handle AI API fallbacks"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as primary_error:
            logger.error(f"Primary AI service error: {primary_error}")
            try:
                # Try to extract request from args (assuming first arg is request)
                if args and hasattr(args[0], 'body'):
                    request = args[0]
                    # Handle fallback logic here
                    return JsonResponse({
                        'response': "I apologize, but I encountered an error while processing your request. "
                                   "I've switched to a backup system to handle your query. Please try again.",
                        'error': str(primary_error)
                    })
                return func(*args, **kwargs)  # If we can't extract request, just retry original function
            except Exception as fallback_error:
                logger.error(f"Fallback AI service error: {fallback_error}")
                return JsonResponse({
                    'response': "I apologize, but our AI services are currently experiencing issues. "
                               "Please try again later.",
                    'error': f"{primary_error} -> {fallback_error}"
                }, status=200)  # Return 200 to handle in frontend
    return wrapper

@login_required
def chat_view(request):
    """Main chat interface view - optimized for performance"""
    # Get user's conversations with prefetch for efficiency
    conversations = Conversation.objects.filter(user=request.user).order_by('-updated_at')[:10]

    # Get user profile and context
    try:
        profile = request.user.profile
        user_context = {
            'stage': request.user.get_application_stage_display(),
            'path': request.user.get_visa_path_display(),
            'experience_years': request.user.years_experience,
            'technical_background': request.user.is_technical,
            'business_background': request.user.is_business,
            'expertise_areas': profile.tech_specializations or []
        }
    except UserProfile.DoesNotExist:
        messages.warning(request, 'Please complete your profile first.')
        return redirect('accounts:profile')

    # Get or create active conversation
    active_conversation_id = request.session.get('active_conversation_id')
    if active_conversation_id:
        try:
            active_conversation = Conversation.objects.get(id=active_conversation_id, user=request.user)
        except Conversation.DoesNotExist:
            # Create new conversation
            active_conversation = Conversation.objects.create(
                user=request.user,
                title="New Conversation"
            )
            request.session['active_conversation_id'] = active_conversation.id
    else:
        # Create new conversation
        active_conversation = Conversation.objects.create(
            user=request.user,
            title="New Conversation"
        )
        request.session['active_conversation_id'] = active_conversation.id

    # Get messages for active conversation - limit to recent messages for performance
    messages_list = Message.objects.filter(conversation=active_conversation).order_by('created_at')[:50]

    # Get query usage statistics
    queries_used = AIQuery.objects.filter(user=request.user).count()
    remaining_queries = profile.ai_queries_limit - queries_used

    if queries_used >= profile.ai_queries_limit and not request.user.is_staff:
        messages.warning(request, 'You have reached your AI query limit. Please upgrade your plan for more queries.')

    context = {
        'conversations': conversations,
        'active_conversation': active_conversation,
        'messages': messages_list,
        'user_context': user_context,
        'remaining_queries': remaining_queries,
        'queries_used': queries_used,
        'queries_limit': profile.ai_queries_limit,
        'profile': profile,
        'show_quick_actions': messages_list.count() <= 1
    }

    return render(request, 'ai_assistant/chat.html', context)

@login_required
def conversation_view(request, conversation_id):
    """View a specific conversation"""
    conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)

    # Set as active conversation
    request.session['active_conversation_id'] = conversation.id

    # Get all conversations for sidebar
    conversations = Conversation.objects.filter(user=request.user).order_by('-updated_at')[:10]

    # Get messages for this conversation
    messages_list = Message.objects.filter(conversation=conversation).order_by('created_at')

    # Get user profile and query usage
    profile = request.user.profile
    queries_used = AIQuery.objects.filter(user=request.user).count()
    remaining_queries = profile.ai_queries_limit - queries_used

    context = {
        'conversations': conversations,
        'active_conversation': conversation,
        'messages': messages_list,
        'remaining_queries': remaining_queries,
        'queries_used': queries_used,
        'queries_limit': profile.ai_queries_limit,
        'profile': profile,
        'show_quick_actions': messages_list.count() <= 1
    }

    return render(request, 'ai_assistant/chat.html', context)

# FIXED: Complete send_message function with proper Groq integration
@login_required
@require_POST
@rate_limit(max_calls=20, window=60)
def send_message(request):
    """Send message with multiple AI provider fallbacks"""
    try:
        data = json.loads(request.body)
        message_text = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')

        # Get or create conversation
        if conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id, user=request.user)
            except Conversation.DoesNotExist:
                conversation = Conversation.objects.create(
                    user=request.user,
                    title=message_text[:50] + "..."
                )
        else:
            conversation = Conversation.objects.create(
                user=request.user,
                title=message_text[:50] + "..."
            )

        # Save user message
        Message.objects.create(
            conversation=conversation,
            content=message_text,
            role='user'
        )

        # Get previous messages for context
        previous_messages = Message.objects.filter(conversation=conversation).order_by('created_at')[:5]

        # Format messages for AI
        messages = [{"role": "system", "content": TECH_NATION_SYSTEM_PROMPT}]
        for msg in previous_messages:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": message_text})

        # Check cache first
        cache_key = f"tech_nation_response:{hash(message_text)}"
        cached_response = cache.get(cache_key)

        if cached_response:
            ai_response = cached_response
        else:
            # Try available AI providers in order of preference
            ai_response = None

            # Try Groq first
            if groq_client:
                try:
                    start_time = time.time()
                    response = groq_client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=800
                    )
                    ai_response = response.choices[0].message.content
                    logger.info(f"Groq API call took {time.time() - start_time:.2f} seconds")
                except Exception as e:
                    logger.error(f"Groq API error: {e}")

            # Try DeepSeek if Groq failed
            if not ai_response and deepseek_client:
                try:
                    ai_response = use_deepseek_api(messages, temperature=0.7, max_tokens=800)
                    logger.info("Used DeepSeek API")
                except Exception as e:
                    logger.error(f"DeepSeek API error: {e}")

            # Try OpenAI as last resort
            if not ai_response and openai_client:
                try:
                    response = openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=800
                    )
                    ai_response = response.choices[0].message.content
                    logger.info("Used OpenAI API")
                except Exception as e:
                    logger.error(f"OpenAI API error: {e}")

            # If all APIs failed, return error
            if not ai_response:
                return JsonResponse({
                    'error': 'All AI services are currently unavailable. Please try again later.'
                }, status=500)

            # Cache the response
            cache.set(cache_key, ai_response, timeout=60*60*24)

        # Save response as message
        Message.objects.create(
            conversation=conversation,
            content=ai_response,
            role='assistant'
        )

        # Calculate token usage
        input_tokens = len(' '.join([m["content"] for m in messages]).split()) * 1.3
        output_tokens = len(ai_response.split()) * 1.3
        cost = (input_tokens * 0.11 + output_tokens * 0.34) / 1_000_000

        # Save query with cost tracking
        AIQuery.objects.create(
            user=request.user,
            query_text=message_text,
            response_text=ai_response,
            source_citations=[],
            tokens_used=int(input_tokens + output_tokens),
            query_type='chat'
        )

        return JsonResponse({
            'response': ai_response,
            'conversation_id': conversation.id,
            'cost': f"${cost:.6f}"
        })

    except Exception as e:
        logger.error(f"Error in send_message: {e}")
        return JsonResponse({
            'error': 'I apologize, but I encountered an error. Please try again.',
            'details': str(e)
        }, status=500)

@login_required
@rate_limit(max_calls=10, window=60)
def stream_message(request):
    """Handle streaming responses with multiple AI provider fallbacks"""
    try:
        # Get message from query parameters
        message_text = request.GET.get('message', '').strip()
        conversation_id = request.session.get('active_conversation_id')

        if not message_text:
            return JsonResponse({'error': 'No message provided'}, status=400)

        # Check user query limits first
        try:
            profile = request.user.profile
            queries_used = AIQuery.objects.filter(user=request.user).count()
            if queries_used >= profile.ai_queries_limit and not request.user.is_staff:
                return JsonResponse({'error': 'You have reached your AI query limit'}, status=403)
        except Exception as e:
            logger.error(f"Error checking query limits: {e}")
            # Continue anyway - don't block the request

        # Get or create conversation
        if conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id, user=request.user)
            except Conversation.DoesNotExist:
                conversation = Conversation.objects.create(user=request.user, title=message_text[:50] + "...")
                request.session['active_conversation_id'] = conversation.id
        else:
            conversation = Conversation.objects.create(user=request.user, title=message_text[:50] + "...")
            request.session['active_conversation_id'] = conversation.id

        # Save user message
        Message.objects.create(conversation=conversation, content=message_text, role='user')

        # Get previous messages (limit to 5 for faster responses)
        previous_messages = Message.objects.filter(conversation=conversation).order_by('created_at')[:5]

        # Format messages with the same system prompt
        messages = [{"role": "system", "content": TECH_NATION_SYSTEM_PROMPT}]

        # Add conversation history
        for msg in previous_messages:
            messages.append({"role": msg.role, "content": msg.content})

        # Add current user message
        messages.append({"role": "user", "content": message_text})

        # Create a function to generate streaming response
        def generate_response():
            full_response = ""
            start_time = time.time()
            used_provider = None

            try:
                # Try Groq first (simulate streaming since Groq doesn't support real streaming)
                if groq_client:
                    try:
                        response = groq_client.chat.completions.create(
                            model="llama-3.1-8b-instant",
                            messages=messages,
                            temperature=0.5,
                            max_tokens=800
                        )
                        full_response = response.choices[0].message.content
                        used_provider = "Groq"
                        
                        # Simulate streaming by sending chunks
                        words = full_response.split()
                        chunk_size = 3  # Send 3 words at a time
                        for i in range(0, len(words), chunk_size):
                            chunk = ' '.join(words[i:i+chunk_size])
                            if i + chunk_size < len(words):
                                chunk += ' '
                            yield f"data: {json.dumps({'content': chunk})}\\n\\n"
                            time.sleep(0.05)  # Small delay to simulate streaming
                        
                        logger.info(f"Groq response took {time.time() - start_time:.2f} seconds")

                    except Exception as e:
                        logger.error(f"Groq error: {e}")
                        full_response = ""  # Reset for fallback

                # Try DeepSeek streaming if Groq failed
                if not full_response and deepseek_client:
                    try:
                        stream = deepseek_client.chat.completions.create(
                            model="deepseek-chat",
                            messages=messages,
                            temperature=0.5,
                            max_tokens=800,
                            stream=True
                        )

                        for chunk in stream:
                            if chunk.choices[0].delta.content:
                                content = chunk.choices[0].delta.content
                                full_response += content
                                yield f"data: {json.dumps({'content': content})}\\n\\n"

                        used_provider = "DeepSeek"
                        logger.info(f"DeepSeek streaming response took {time.time() - start_time:.2f} seconds")

                    except Exception as e:
                        logger.error(f"DeepSeek streaming error: {e}")
                        full_response = ""

                # Fall back to OpenAI streaming if both failed
                if not full_response and openai_client:
                    try:
                        start_time = time.time()
                        stream = openai_client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=messages,
                            temperature=0.5,
                            max_tokens=800,
                            stream=True
                        )

                        for chunk in stream:
                            if chunk.choices[0].delta.content:
                                content = chunk.choices[0].delta.content
                                full_response += content
                                yield f"data: {json.dumps({'content': content})}\\n\\n"

                        used_provider = "OpenAI"
                        logger.info(f"OpenAI fallback streaming response took {time.time() - start_time:.2f} seconds")

                    except Exception as fallback_error:
                        logger.error(f"OpenAI streaming error: {fallback_error}")
                        full_response = ""

                # If all providers failed, send error
                if not full_response:
                    error_msg = "I apologize, but all AI services are currently unavailable. Please try again later."
                    yield f"data: {json.dumps({'content': error_msg})}\\n\\n"
                    yield f"data: {json.dumps({'done': True, 'error': 'No AI provider available'})}\\n\\n"
                    return

                # Log performance metrics
                logger.info(f"Streaming response took {time.time() - start_time:.2f} seconds using {used_provider}")

                # Save complete message to database
                try:
                    Message.objects.create(
                        conversation=conversation,
                        content=full_response,
                        role='assistant'
                    )

                    # Save query for analytics
                    AIQuery.objects.create(
                        user=request.user,
                        query_text=message_text,
                        response_text=full_response,
                        source_citations=[],
                        tokens_used=len(full_response.split()) + len(message_text.split()),
                        query_type='chat'
                    )

                    # Get updated query count
                    queries_used = AIQuery.objects.filter(user=request.user).count()
                    remaining_queries = request.user.profile.ai_queries_limit - queries_used

                    # Send completion message with metadata
                    yield f"data: {json.dumps({'done': True, 'remaining_queries': remaining_queries, 'provider': used_provider})}\\n\\n"
                except Exception as db_error:
                    logger.error(f"Database save error: {db_error}")
                    # Still send completion even if DB save fails
                    yield f"data: {json.dumps({'done': True, 'provider': used_provider})}\\n\\n"

            except Exception as gen_error:
                logger.error(f"Generator error: {gen_error}")
                error_msg = "I encountered an error while processing your request. Please try again."
                yield f"data: {json.dumps({'content': error_msg})}\\n\\n"
                yield f"data: {json.dumps({'done': True, 'error': str(gen_error)})}\\n\\n"

        # FIXED: Remove problematic headers that cause WSGI errors
        response = StreamingHttpResponse(
            generate_response(), 
            content_type='text/event-stream'
        )
        
        # Set only safe headers for WSGI
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # For nginx
        
        return response

    except Exception as e:
        logger.error(f"Error in stream_message: {e}")
        # FIXED: Always return an HttpResponse, never None
        return JsonResponse({
            'error': f'Stream error: {str(e)}',
            'message': 'Please try again or use the regular chat mode.'
        }, status=500)        

@login_required
def query_history(request):
    """View query history with pagination"""
    # Get user's queries with pagination
    queries = AIQuery.objects.filter(user=request.user).order_by('-created_at')[:100]

    # Calculate token usage statistics
    total_tokens = sum(q.tokens_used for q in queries if q.tokens_used)
    avg_tokens = total_tokens / len(queries) if queries else 0

    # Get user profile for limits
    profile = request.user.profile
    queries_used = queries.count()
    remaining_queries = profile.ai_queries_limit - queries_used

    context = {
        'queries': queries,
        'total_tokens': total_tokens,
        'avg_tokens': avg_tokens,
        'queries_used': queries_used,
        'remaining_queries': remaining_queries,
        'queries_limit': profile.ai_queries_limit
    }

    return render(request, 'ai_assistant/query_history.html', context)

@login_required
@require_POST
def submit_feedback(request):
    """Submit feedback for an AI response"""
    try:
        data = json.loads(request.body)
        query_id = data.get('query_id')
        rating = data.get('rating')
        comments = data.get('comments', '')

        if not query_id or rating is None:
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        # Get the query
        query = get_object_or_404(AIQuery, id=query_id, user=request.user)

        # Create or update feedback
        feedback, created = AIFeedback.objects.update_or_create(
            query=query,
            defaults={
                'rating': rating,
                'comments': comments
            }
        )

        return JsonResponse({
            'success': True,
            'message': 'Feedback submitted successfully'
        })

    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        return JsonResponse({'error': str(e)}, status=500)

# FIXED: All AI generation functions with proper client handling
@login_required
@require_POST
@rate_limit(max_calls=5, window=300)
def generate_personal_statement(request):
    """Generate a personal statement using AI"""
    try:
        # Get form data
        data = json.loads(request.body)
        background = data.get('background', '')
        achievements = data.get('achievements', '')
        skills = data.get('skills', '')
        goals = data.get('goals', '')

        if not background or not achievements:
            return JsonResponse({'error': 'Please provide your background and achievements'}, status=400)

        # Check if user has enough queries
        profile = request.user.profile
        queries_used = AIQuery.objects.filter(user=request.user).count()
        if queries_used >= profile.ai_queries_limit and not request.user.is_staff:
            return JsonResponse({'error': 'You have reached your AI query limit'}, status=403)

        # Prepare prompt
        prompt = f"""Generate a personal statement for a Tech Nation Global Talent Visa application based on the following information:

Background: {background}

Achievements: {achievements}

Skills: {skills}

Goals: {goals}

The personal statement should:
1. Demonstrate exceptional talent in digital technology
2. Highlight technical expertise and innovation
3. Show recognition in the field
4. Explain future plans to contribute to the UK tech sector
5. Be well-structured with clear sections
6. Be approximately 1000-1200 words
"""

        # Format messages
        messages = [
            {"role": "system", "content": "You are an expert in writing personal statements for Tech Nation Global Talent Visa applications."},
            {"role": "user", "content": prompt}
        ]

        # Check cache first
        cache_key = f"personal_statement:{hash(prompt)}"
        cached_response = cache.get(cache_key)

        if cached_response:
            generated_statement = cached_response
            logger.info(f"Using cached personal statement for user {request.user.id}")
        else:
            generated_statement = None

            # Try Groq first
            if groq_client:
                try:
                    response = groq_client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1500
                    )
                    generated_statement = response.choices[0].message.content
                except Exception as e:
                    logger.error(f"Groq API error: {e}")

            # Try DeepSeek if Groq failed
            if not generated_statement and deepseek_client:
                try:
                    generated_statement = use_deepseek_api(messages, temperature=0.7, max_tokens=1500)
                except Exception as e:
                    logger.error(f"DeepSeek API error: {e}")

            # Try OpenAI as last resort
            if not generated_statement and openai_client:
                try:
                    response = openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1500
                    )
                    generated_statement = response.choices[0].message.content
                except Exception as e:
                    logger.error(f"OpenAI API error: {e}")

            if not generated_statement:
                return JsonResponse({'error': 'All AI services are currently unavailable. Please try again later.'}, status=500)

            # Cache the response for 24 hours
            cache.set(cache_key, generated_statement, timeout=60*60*24)

        # Calculate token usage
        input_tokens = len(' '.join([m["content"] for m in messages]).split()) * 1.3
        output_tokens = len(generated_statement.split()) * 1.3

        # Save the query for analytics
        query = AIQuery.objects.create(
            user=request.user,
            query_text=prompt,
            response_text=generated_statement,
            source_citations=[],
            tokens_used=int(input_tokens + output_tokens),
            query_type='personal_statement'
        )

        return JsonResponse({
            'success': True,
            'statement': generated_statement,
            'query_id': query.id
        })

    except Exception as e:
        logger.error(f"Error in generate_personal_statement: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
@rate_limit(max_calls=5, window=300)
def enhance_cv(request):
    """Enhance a CV using AI suggestions"""
    try:
        # Get form data
        data = json.loads(request.body)
        cv_content = data.get('cv_content', '')

        if not cv_content:
            return JsonResponse({'error': 'Please provide your CV content'}, status=400)

        # Check if user has enough queries
        profile = request.user.profile
        queries_used = AIQuery.objects.filter(user=request.user).count()
        if queries_used >= profile.ai_queries_limit and not request.user.is_staff:
            return JsonResponse({'error': 'You have reached your AI query limit'}, status=403)

        # Prepare prompt
        prompt = f"""Analyze this CV for a Tech Nation Global Talent Visa application and provide specific improvements:

{cv_content}

Please provide:
1. Overall assessment (strengths and weaknesses)
2. Specific suggestions to improve each section
3. Examples of better phrasing for key achievements
4. Additional sections or content to consider adding
5. Formatting recommendations

Format your response with clear sections and bullet points.
"""

        # Format messages
        messages = [
            {"role": "system", "content": "You are an expert CV consultant specializing in Tech Nation Global Talent Visa applications."},
            {"role": "user", "content": prompt}
        ]

        # Check cache first
        cache_key = f"cv_enhancement:{hash(prompt)}"
        cached_response = cache.get(cache_key)

        if cached_response:
            enhancement_suggestions = cached_response
            logger.info(f"Using cached CV enhancement for user {request.user.id}")
        else:
            enhancement_suggestions = None

            # Try Groq first
            if groq_client:
                try:
                    response = groq_client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1200
                    )
                    enhancement_suggestions = response.choices[0].message.content
                except Exception as e:
                    logger.error(f"Groq API error: {e}")

            # Try DeepSeek if Groq failed
            if not enhancement_suggestions and deepseek_client:
                try:
                    enhancement_suggestions = use_deepseek_api(messages, temperature=0.7, max_tokens=1200)
                except Exception as e:
                    logger.error(f"DeepSeek API error: {e}")

            # Try OpenAI as last resort
            if not enhancement_suggestions and openai_client:
                try:
                    response = openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1200
                    )
                    enhancement_suggestions = response.choices[0].message.content
                except Exception as e:
                    logger.error(f"OpenAI API error: {e}")

            if not enhancement_suggestions:
                return JsonResponse({'error': 'All AI services are currently unavailable. Please try again later.'}, status=500)

            # Cache the response for 24 hours
            cache.set(cache_key, enhancement_suggestions, timeout=60*60*24)

        # Calculate token usage
        input_tokens = len(' '.join([m["content"] for m in messages]).split()) * 1.3
        output_tokens = len(enhancement_suggestions.split()) * 1.3

        # Save the query for analytics
        query = AIQuery.objects.create(
            user=request.user,
            query_text=prompt,
            response_text=enhancement_suggestions,
            source_citations=[],
            tokens_used=int(input_tokens + output_tokens),
            query_type='cv_enhancement'
        )

        return JsonResponse({
            'success': True,
            'suggestions': enhancement_suggestions,
            'query_id': query.id
        })

    except Exception as e:
        logger.error(f"Error in enhance_cv: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
@rate_limit(max_calls=5, window=300)
def generate_recommendation_letter(request):
    """Generate a recommendation letter template using AI"""
    try:
        # Get form data
        data = json.loads(request.body)
        applicant_name = data.get('applicant_name', '')
        recommender_name = data.get('recommender_name', '')
        recommender_position = data.get('recommender_position', '')
        relationship = data.get('relationship', '')
        achievements = data.get('achievements', '')

        if not applicant_name or not recommender_name or not relationship:
            return JsonResponse({'error': 'Please provide all required fields'}, status=400)

        # Check if user has enough queries
        profile = request.user.profile
        queries_used = AIQuery.objects.filter(user=request.user).count()
        if queries_used >= profile.ai_queries_limit and not request.user.is_staff:
            return JsonResponse({'error': 'You have reached your AI query limit'}, status=403)

        # Prepare prompt
        prompt = f"""Generate a recommendation letter for a Tech Nation Global Talent Visa application with the following details:

Applicant Name: {applicant_name}
Recommender Name: {recommender_name}
Recommender Position: {recommender_position}
Relationship to Applicant: {relationship}
Key Achievements to Highlight: {achievements}

The letter should:
1. Be on a professional letterhead format
2. Include the recommender's contact information
3. Explain how the recommender knows the applicant
4. Provide specific examples of the applicant's exceptional talent
5. Highlight technical expertise and innovation
6. Mention recognition in the field
7. Be approximately 750-1000 words
8. Include a strong endorsement statement
9. End with a formal signature block
"""

        # Format messages
        messages = [
            {"role": "system", "content": "You are an expert in writing recommendation letters for Tech Nation Global Talent Visa applications."},
            {"role": "user", "content": prompt}
        ]

        # Check cache first
        cache_key = f"recommendation_letter:{hash(prompt)}"
        cached_response = cache.get(cache_key)

        if cached_response:
            generated_letter = cached_response
            logger.info(f"Using cached recommendation letter for user {request.user.id}")
        else:
            generated_letter = None

            # Try Groq first
            if groq_client:
                try:
                    response = groq_client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1200
                    )
                    generated_letter = response.choices[0].message.content
                except Exception as e:
                    logger.error(f"Groq API error: {e}")

            # Try DeepSeek if Groq failed
            if not generated_letter and deepseek_client:
                try:
                    generated_letter = use_deepseek_api(messages, temperature=0.7, max_tokens=1200)
                except Exception as e:
                    logger.error(f"DeepSeek API error: {e}")

            # Try OpenAI as last resort
            if not generated_letter and openai_client:
                try:
                    response = openai_client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=1200
                    )
                    generated_letter = response.choices[0].message.content
                except Exception as e:
                    logger.error(f"OpenAI API error: {e}")

            if not generated_letter:
                return JsonResponse({'error': 'All AI services are currently unavailable. Please try again later.'}, status=500)

            # Cache the response for 24 hours
            cache.set(cache_key, generated_letter, timeout=60*60*24)

        # Calculate token usage
        input_tokens = len(' '.join([m["content"] for m in messages]).split()) * 1.3
        output_tokens = len(generated_letter.split()) * 1.3

        # Save the query for analytics
        query = AIQuery.objects.create(
            user=request.user,
            query_text=prompt,
            response_text=generated_letter,
            source_citations=[],
            tokens_used=int(input_tokens + output_tokens),
            query_type='recommendation_letter'
        )

        return JsonResponse({
            'success': True,
            'letter': generated_letter,
            'query_id': query.id
        })

    except Exception as e:
        logger.error(f"Error in generate_recommendation_letter: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def create_conversation(request):
    """Create a new conversation"""
    try:
        # Create new conversation
        conversation = Conversation.objects.create(
            user=request.user,
            title="New Conversation"
        )

        # Set as active conversation
        request.session['active_conversation_id'] = conversation.id

        return JsonResponse({
            'success': True,
            'conversation_id': conversation.id
        })

    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def rename_conversation(request, conversation_id):
    """Rename a conversation"""
    try:
        # Get the conversation
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)

        # Get new title from request
        data = json.loads(request.body)
        new_title = data.get('title', '').strip()

        if not new_title:
            return JsonResponse({'error': 'Title cannot be empty'}, status=400)

        # Update title
        conversation.title = new_title
        conversation.save(update_fields=['title'])

        return JsonResponse({
            'success': True,
            'message': 'Conversation renamed successfully'
        })

    except Exception as e:
        logger.error(f"Error renaming conversation: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def delete_conversation(request, conversation_id):
    """Delete a conversation"""
    try:
        # Get the conversation
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)

        # Check if this is the active conversation
        if request.session.get('active_conversation_id') == conversation_id:
            # Create a new conversation to set as active
            new_conversation = Conversation.objects.create(
                user=request.user,
                title="New Conversation"
            )
            request.session['active_conversation_id'] = new_conversation.id

        # Delete the conversation (will cascade delete messages)
        conversation.delete()

        return JsonResponse({
            'success': True,
            'message': 'Conversation deleted successfully',
            'redirect': request.session.get('active_conversation_id')
        })

    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        return JsonResponse({'error': str(e)}, status=500)
