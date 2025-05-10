from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from django.conf import settings
import logging
import os

logger = logging.getLogger(__name__)

class DocumentGenerator:
    def __init__(self):
        # Check if OpenAI API key is set
        openai_api_key = getattr(settings, 'OPENAI_API_KEY', os.environ.get('OPENAI_API_KEY', ''))
        if not openai_api_key:
            logger.warning("OpenAI API key not found. Document generation will not function properly.")
            openai_api_key = "dummy_key"  # Placeholder to avoid errors during initialization

        try:
            self.llm = ChatOpenAI(
                model_name="gpt-4o",
                temperature=0.7,
                openai_api_key=openai_api_key
            )
            self.api_key_valid = openai_api_key != "dummy_key"
        except Exception as e:
            logger.error(f"Error initializing ChatOpenAI: {e}")
            self.llm = None
            self.api_key_valid = False

    def generate_personal_statement(self, user_info):
        """Generate a personal statement based on user information"""
        if not self.api_key_valid or not self.llm:
            return "Document generation is not available. Please configure the OpenAI API key."

        template = """
        You are an expert in writing personal statements for the Tech Nation Global Talent Visa.
        Create a compelling personal statement for a tech professional with the following information:

        Name: {name}
        Current Role: {current_role}
        Years of Experience: {years_experience}
        Specialization: {specialization}
        Key Achievements: {achievements}
        Future Plans in the UK: {future_plans}

        The personal statement should:
        1. Be approximately 1000-1500 words
        2. Highlight how the applicant meets the Tech Nation mandatory and optional criteria
        3. Demonstrate the applicant's exceptional talent or promise
        4. Show how they will contribute to the UK tech ecosystem
        5. Be written in first person
        6. Include specific examples and achievements
        7. Be structured with clear paragraphs and headings

        Personal Statement:
        """

        try:
            prompt = PromptTemplate(
                template=template,
                input_variables=["name", "current_role", "years_experience", "specialization", "achievements", "future_plans"]
            )

            formatted_prompt = prompt.format(**user_info)
            response = self.llm.invoke(formatted_prompt)

            return response.content
        except Exception as e:
            logger.error(f"Error generating personal statement: {e}")
            return "An error occurred while generating the personal statement. Please try again later."

    def enhance_cv(self, cv_text, user_info):
        """Enhance a CV for the Tech Nation Global Talent Visa application"""
        if not self.api_key_valid or not self.llm:
            return "Document generation is not available. Please configure the OpenAI API key."

        template = """
        You are an expert in optimizing CVs for the Tech Nation Global Talent Visa.
        Enhance the following CV to better align with the Tech Nation criteria and make it more compelling.

        Applicant Information:
        Specialization: {specialization}
        Target Criteria: {target_criteria}

        Original CV:
        {cv_text}

        Please:
        1. Restructure the CV if needed for better impact
        2. Highlight achievements that align with Tech Nation criteria
        3. Quantify achievements where possible
        4. Add relevant keywords for the tech industry
        5. Ensure the format is clean and professional
        6. Keep the length to 2-3 pages

        Enhanced CV:
        """

        try:
            prompt = PromptTemplate(
                template=template,
                input_variables=["cv_text", "specialization", "target_criteria"]
            )

            formatted_prompt = prompt.format(
                cv_text=cv_text,
                specialization=user_info.get('specialization', ''),
                target_criteria=user_info.get('target_criteria', '')
            )

            response = self.llm.invoke(formatted_prompt)

            return response.content
        except Exception as e:
            logger.error(f"Error enhancing CV: {e}")
            return "An error occurred while enhancing the CV. Please try again later."

    def generate_recommendation_letter(self, recommender_info, applicant_info):
        """Generate a recommendation letter template"""
        if not self.api_key_valid or not self.llm:
            return "Document generation is not available. Please configure the OpenAI API key."

        template = """
        You are an expert in writing recommendation letters for the Tech Nation Global Talent Visa.
        Create a compelling recommendation letter from a referee with the following information:

        Recommender Information:
        Name: {recommender_name}
        Position: {recommender_position}
        Company: {recommender_company}
        Relationship to Applicant: {relationship}

        Applicant Information:
        Name: {applicant_name}
        Current Role: {applicant_role}
        Specialization: {applicant_specialization}
        Key Strengths: {key_strengths}

        The recommendation letter should:
        1. Be approximately 750-1000 words
        2. Confirm the recommender's credentials and relationship to the applicant
        3. Provide specific examples of the applicant's exceptional talent or promise
        4. Explain how the applicant meets the Tech Nation criteria
        5. Include a strong endorsement for the visa application
        6. Be written on a professional letterhead (provide placeholder for this)

        Recommendation Letter:
        """

        try:
            prompt = PromptTemplate(
                template=template,
                input_variables=[
                    "recommender_name", "recommender_position", "recommender_company",
                    "relationship", "applicant_name", "applicant_role",
                    "applicant_specialization", "key_strengths"
                ]
            )

            # Combine the dictionaries
            all_info = {**recommender_info, **applicant_info}

            formatted_prompt = prompt.format(**all_info)
            response = self.llm.invoke(formatted_prompt)

            return response.content
        except Exception as e:
            logger.error(f"Error generating recommendation letter: {e}")
            return "An error occurred while generating the recommendation letter. Please try again later."

# Initialize the document generator
document_generator = DocumentGenerator()