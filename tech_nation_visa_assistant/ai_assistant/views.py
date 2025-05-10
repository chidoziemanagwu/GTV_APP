from django.shortcuts import render, redirect
from django.http import JsonResponse
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
from django.contrib import messages
from openai import OpenAI
from django.core.cache import cache
from django.http import StreamingHttpResponse


logger = logging.getLogger(__name__)


# Configure OpenAI API
client = OpenAI(api_key=settings.OPENAI_API_KEY)

    
    # Initialize document generator
document_generator = DocumentGenerator()





@login_required
def chat_view(request):
    """Main chat interface view"""
    # Get user's conversations for sidebar
    conversations = Conversation.objects.filter(user=request.user).order_by('-updated_at')

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
            # Create new conversation with welcome message
            active_conversation = Conversation.objects.create(
                user=request.user,
                title="New Conversation"
            )
            # Add AI welcome message
            # Message.objects.create(
            #     conversation=active_conversation,
            #     content="Welcome to the Tech Nation Visa Assistant! I'm here to help you with your Global Talent Visa application. What would you like to know about the Tech Nation endorsement process?",
            #     role='assistant'
            # )
            request.session['active_conversation_id'] = active_conversation.id
    else:
        # Create new conversation with welcome message
        active_conversation = Conversation.objects.create(
            user=request.user,
            title="New Conversation"
        )
        # Add AI welcome message
        # Message.objects.create(
        #     conversation=active_conversation,
        #     content="Welcome to the Tech Nation Visa Assistant! I'm here to help you with your Global Talent Visa application. What would you like to know about the Tech Nation endorsement process?",
        #     role='assistant'
        # )
        request.session['active_conversation_id'] = active_conversation.id

    # Get messages for active conversation
    messages_list = Message.objects.filter(conversation=active_conversation).order_by('created_at')

    # Get query usage statistics
    queries_used = AIQuery.objects.filter(user=request.user).count()
    remaining_queries = profile.ai_queries_limit - queries_used

    if queries_used >= profile.ai_queries_limit and not request.user.is_staff:
        messages.warning(request, 'You have reached your AI query limit. Please upgrade your plan for more queries.')
        # return redirect('payments:subscription_plans')

    context = {
        'conversations': conversations,
        'active_conversation': active_conversation,
        'messages': messages_list,
        'user_context': user_context,
        'remaining_queries': remaining_queries,
        'queries_used': queries_used,
        'queries_limit': profile.ai_queries_limit,
        'profile': profile,
        'show_quick_actions': messages_list.count() <= 1  # Show quick actions if only welcome message exists
    }

    return render(request, 'ai_assistant/chat.html', context)




@login_required
@require_POST
def send_message(request):
    """Handle sending messages to ChatGPT for Tech Nation visa queries"""
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

        # Get previous messages for context (limit to last 10)
        previous_messages = Message.objects.filter(conversation=conversation).order_by('created_at')[:5]

        # Format messages for OpenAI
        messages = [
            {"role": "system", "content": """You are a specialized assistant for the Tech Nation Global Talent Visa.
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

            <div class="disclaimer">*Disclaimer: While we strive to provide up-to-date information, please verify details on the [official Tech Nation website](https://technation.io/global-talent-visa/) for the latest guidance.*</div>"""}
        ]

        # Add conversation history
        for msg in previous_messages:
            messages.append({"role": msg.role, "content": msg.content})

        # Add current user message
        messages.append({"role": "user", "content": message_text})


        cache_key = f"tech_nation_response:{message_text}"
        cached_response = cache.get(cache_key)

        if cached_response:
            # Use cached response
            ai_response = cached_response
        else:
            # Call OpenAI API
            try:
                response = client.chat.completions.create(
                    model="gpt-4.1-nano",  # or "gpt-3.5-turbo" if you prefer
                    messages=messages,
                    temperature=0.7,
                    max_tokens=500
                )

                ai_response = response.choices[0].message.content

                # Save the query for analytics
                AIQuery.objects.create(
                    user=request.user,
                    query_text=message_text,
                    response_text=ai_response,
                    source_citations=[]
                )

            except Exception as e:
                logger.error(f"Error calling OpenAI API: {e}")
                ai_response = (
                    "I apologize, but I encountered an error while processing your request. "
                    "Please try again later or rephrase your question.\n\n"
                    "*Disclaimer: While we strive to provide up-to-date information, please verify details on the "
                    "[official Tech Nation website](https://technation.io/global-talent-visa/) for the latest guidance.*"
                )


            cache.set(cache_key, ai_response, timeout=60*60*24)  # Cache for 24 hours
        # Save response as message
        Message.objects.create(
            conversation=conversation,
            content=ai_response,
            role='assistant'
        )

        # Update conversation timestamp
        conversation.save()

        # Get updated query count
        queries_used = AIQuery.objects.filter(user=request.user).count()
        remaining_queries = request.user.profile.ai_queries_limit - queries_used

        return JsonResponse({
            'response': ai_response,
            'conversation_id': conversation.id,
            'remaining_queries': remaining_queries
        })

    except Exception as e:
        logger.error(f"Error in send_message: {e}")
        return JsonResponse({
            'response': "I apologize, but I encountered an error while processing your request. Please try again.\n\n"
                       "*Disclaimer: While we strive to provide up-to-date information, please verify details on the "
                       "[official Tech Nation website](https://technation.io/global-talent-visa/) for the latest guidance.*",
            'error': str(e)
        }, status=200)  # Return 200 to handle in the frontend


@login_required
@require_POST
def submit_feedback(request):
    """Handle feedback submission for AI responses"""
    try:
        data = json.loads(request.body)
        query_id = data.get('query_id')
        rating = data.get('rating')
        comment = data.get('comment', '')

        query = AIQuery.objects.get(id=query_id, user=request.user)

        feedback = AIFeedback.objects.create(
            query=query,
            rating=rating,
            comment=comment
        )

        return JsonResponse({
            'success': True,
            'message': 'Feedback submitted successfully'
        })

    except AIQuery.DoesNotExist:
        return JsonResponse({
            'error': 'Query not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
def conversation_view(request, conversation_id):
    """View a specific conversation"""
    try:
        conversation = Conversation.objects.get(id=conversation_id, user=request.user)
        messages = Message.objects.filter(conversation=conversation).order_by('created_at')
        conversations = Conversation.objects.filter(user=request.user).order_by('-updated_at')

        return render(request, 'ai_assistant/conversation.html', {
            'conversation': conversation,
            'messages': messages,
            'conversations': conversations
        })
    except Conversation.DoesNotExist:
        messages.error(request, 'Conversation not found.')
        return redirect('ai_assistant:chat')

@login_required
def query_history(request):
    """View query history"""
    queries = AIQuery.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'ai_assistant/query_history.html', {
        'queries': queries
    })



# Document Generation Views
@login_required
@require_POST
def generate_personal_statement(request):
    """Generate personal statement"""
    try:
        data = json.loads(request.body)
        personal_statement = document_generator.generate_personal_statement(data)
        return JsonResponse({'personal_statement': personal_statement})
    except Exception as e:
        logger.error(f"Error generating personal statement: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def enhance_cv(request):
    """Enhance CV"""
    try:
        data = json.loads(request.body)
        enhanced_cv = document_generator.enhance_cv(
            data.get('cv_text', ''),
            {
                'specialization': data.get('specialization', ''),
                'target_criteria': data.get('target_criteria', '')
            }
        )
        return JsonResponse({'enhanced_cv': enhanced_cv})
    except Exception as e:
        logger.error(f"Error enhancing CV: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def generate_recommendation_letter(request):
    """Generate recommendation letter"""
    try:
        data = json.loads(request.body)
        letter = document_generator.generate_recommendation_letter(
            data.get('recommender_info', {}),
            data.get('applicant_info', {})
        )
        return JsonResponse({'recommendation_letter': letter})
    except Exception as e:
        logger.error(f"Error generating recommendation letter: {e}")
        return JsonResponse({'error': str(e)}, status=500)

# Conversation Management Views
@login_required
@require_POST
def create_conversation(request):
    """Create a new conversation"""
    conversation = Conversation.objects.create(
        user=request.user,
        title="New Conversation"
    )
    return JsonResponse({
        'id': conversation.id,
        'title': conversation.title
    })

@login_required
@require_POST
def rename_conversation(request, conversation_id):
    """Rename a conversation"""
    try:
        data = json.loads(request.body)
        conversation = Conversation.objects.get(id=conversation_id, user=request.user)
        conversation.title = data.get('title', 'Untitled')
        conversation.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def delete_conversation(request, conversation_id):
    """Delete a conversation"""
    try:
        conversation = Conversation.objects.get(id=conversation_id, user=request.user)
        conversation.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)





@login_required
# Remove the @require_POST decorator
def stream_message(request):
    """Handle streaming responses for ChatGPT"""
    try:
        # Get message from query parameters instead of JSON body
        message_text = request.GET.get('message', '').strip()
        conversation_id = request.session.get('active_conversation_id')

        if not message_text:
            return JsonResponse({'error': 'No message provided'}, status=400)

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
        messages = [
            {"role": "system", "content": """You are a specialized assistant for the Tech Nation Global Talent Visa.
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

            <div class="disclaimer">*Disclaimer: While we strive to provide up-to-date information, please verify details on the [official Tech Nation website](https://technation.io/global-talent-visa/) for the latest guidance.*</div>"""}
        ]

        # Add conversation history
        for msg in previous_messages:
            messages.append({"role": msg.role, "content": msg.content})

        # Add current user message
        messages.append({"role": "user", "content": message_text})

        # Create a function to generate streaming response
        def generate_response():
            full_response = ""

            # Stream the response
            stream = client.chat.completions.create(
                model="gpt-4.1-nano",
                messages=messages,
                temperature=0.5,
                max_tokens=800,
                stream=True
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield f"data: {json.dumps({'content': content})}\n\n"

            # Save complete message to database
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
                source_citations=[]
            )

            # Get updated query count
            queries_used = AIQuery.objects.filter(user=request.user).count()
            remaining_queries = request.user.profile.ai_queries_limit - queries_used

            # Send completion message with metadata
            yield f"data: {json.dumps({'done': True, 'remaining_queries': remaining_queries})}\n\n"

        return StreamingHttpResponse(generate_response(), content_type='text/event-stream')

    except Exception as e:
        logger.error(f"Error in stream_message: {e}")
        return JsonResponse({'error': str(e)}, status=500)