import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

# Updated imports for LangChain
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.docstore.document import Document

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TechNationRAG:
    def __init__(self, openai_api_key: str):
        """Initialize the RAG system with the latest Tech Nation guide content"""
        try:
            self.llm = ChatOpenAI(
                temperature=0,
                model_name="gpt-4-turbo-preview",
                openai_api_key=openai_api_key,
                streaming=True,
                max_tokens=4000
            )

            self.embeddings = OpenAIEmbeddings(
                openai_api_key=openai_api_key,
                model="text-embedding-3-large"
            )

            # Initialize metadata
            self.guide_metadata = {
                "last_updated": "2025-01-22",
                "version": "1.0",
                "source_url": "https://technation-globaltalentvisa-guide.notion.site/",
                "sections": {}
            }

            # Load guide content
            self.guide_content = self._load_guide_content()

            # Initialize vector store
            self._initialize_vector_store()

            logger.info("TechNationRAG initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize TechNationRAG: {e}")
            raise

    def _load_guide_content(self) -> str:
        """Load and return the Tech Nation guide content"""
        return """
# Tech Nation Global Talent Visa Guide

Last Updated: 22nd January 2025
Version: 1.0

## Introduction

The Global Talent Visa enables the brightest and best tech talent from around the world to come and work in the UK's digital technology sector. Tech Nation is the designated endorsing body for digital technology applications.

## Visa Overview

- Valid for up to 5 years
- Allows you to work, change employers, or be self-employed
- Can be extended to immediate family members
- Path to permanent settlement
- No sponsorship required
- No minimum salary requirement
- English language requirement only for settlement

## Eligibility Paths

### 1. Exceptional Talent
For established leaders in the digital technology sector.

Requirements:
- Recognition as a leading talent in digital technology
- Significant achievements in the last 5 years
- Must meet at least 2 of 4 qualifying criteria
- Proven track record of innovation
- Senior-level experience

### 2. Exceptional Promise
For emerging leaders in digital technology.

Requirements:
- Recognition as having potential to be a leading talent
- Achievements in the last 5 years
- Must meet at least 2 of 4 qualifying criteria
- Evidence of innovation potential
- Early-stage career

## Qualifying Criteria

### Exceptional Talent Criteria

Must meet at least 2 of these criteria:

1. Innovation Track Record
- Founded/led a successful product-led digital company
- Senior executive role with significant impact
- Key contributions to innovative digital products

2. Recognition Beyond Role
- Speaking at recognized conferences
- Winning prestigious awards
- Industry recognition and press coverage
- Significant social media influence in tech

3. Technical/Business Contributions
- Significant technical innovations
- Commercial impact in digital businesses
- Board member or senior executive experience
- Notable entrepreneurial achievements

4. Academic Contributions
- Published research papers
- Patents granted
- PhD in relevant field
- Research endorsed by experts

### Exceptional Promise Criteria

Must meet at least 2 of these criteria:

1. Innovation Potential
- Founded a growing digital company
- Key team member in innovative projects
- Emerging technical or business expertise

2. Recognition
- Speaking at industry events
- Rising star awards
- Growing industry recognition
- Emerging thought leadership

3. Technical/Business Achievements
- Growing technical portfolio
- Business impact in digital sector
- Early-stage leadership experience
- Startup experience

4. Academic Achievements
- Research contributions
- Academic qualifications
- Industry-relevant certifications
- Expert endorsements

## Required Documents

1. Personal Statement (1000 words max)
- Career background
- Achievements and impact
- Future plans in UK
- Contribution to UK tech sector

2. CV (3 pages max)
- Detailed work history
- Key achievements
- Publications/presentations
- Awards and recognition

3. Letters of Recommendation (3 required)
- From recognized experts
- Maximum 3 pages each
- Must know work for 12+ months
- Specific to Global Talent application

4. Supporting Evidence (10 documents max)
- 3 pages per document
- English translations required
- Must be verifiable
- No duplicates across criteria

## Fast Track Options

Eligible if accepted into these accelerators:
- Antler
- Bethnal Green Ventures
- Entrepreneur First
- Founders Factory
- Techstars
- [Other approved accelerators]

Benefits:
- 3-week decision target
- Simplified evidence requirements
- Priority processing

## Technical Skills Examples

- DevOps/SysOps
- Software Engineering
- Data Science/Engineering
- AI/ML/NLP
- Cybersecurity
- Hardware Engineering
- Frontend Development
- Operating Systems
- Game Development
- UX/UI Design
- Mobile Development
- Backend Development
- CTO/VP Engineering
- AR/VR Development

## Business Skills Examples

- VC Investment (£25m+)
- Commercial Leadership
- Product Management
- Enterprise Sales
- Growth Strategy
- Digital Marketing
- C-Suite Experience
- Operations Leadership

## Application Process

1. Preparation
- Gather all documents
- Prepare evidence
- Get recommendations
- Write personal statement

2. Submission
- Complete online form
- Pay endorsement fee
- Submit all documents
- Provide translations

3. Assessment
- Technical review
- Expert assessment
- Decision within 8 weeks
- Fast track if eligible

4. Post-Decision
- If endorsed, apply for visa
- If rejected, feedback provided
- Appeal process available
- Reapplication possible

## Exclusions

Not typically suitable for:
- Service delivery roles
- Outsourcing/consulting
- Corporate IT support
- Junior positions
- Non-digital sectors

## Settlement Path

- Apply after 3 or 5 years
- Continuous residence required
- English language requirement
- Life in UK test
- No minimum salary

## Family Members

- Spouse/partner eligible
- Children under 18 eligible
- No additional endorsement
- Same visa duration
- Independent work rights

## Fees and Timeframes

Endorsement:
- Standard: £456
- Fast track available
- 8-week processing
- Priority options

Visa (post-endorsement):
- Up to 5 years
- Extensions possible
- Settlement options
- NHS surcharge applies

## Additional Information

1. Working Rights
- Multiple employers allowed
- Self-employment permitted
- Start/run businesses
- No minimum salary
- No sponsorship needed

2. Geographic Flexibility
- Work anywhere in UK
- Change locations freely
- Remote work allowed
- International travel permitted

3. Switching
- Available from most visas
- In-country applications
- No leaving UK required
- Continuous residence maintained

4. Extensions
- Apply before expiry
- Show continued activity
- No new endorsement
- 5-year extensions

## Success Factors

1. Evidence Quality
- Detailed documentation
- Clear achievements
- Verifiable claims
- Recent activity

2. Recommendation Strength
- Expert credibility
- Detailed knowledge
- Specific examples
- Clear endorsement

3. Personal Statement
- Clear narrative
- Specific plans
- UK benefit
- Future impact

4. Technical/Business Focus
- Clear specialization
- Proven expertise
- Industry impact
- Future potential

## Common Mistakes

1. Documentation
- Missing translations
- Expired documents
- Incomplete evidence
- Poor organization

2. Recommendations
- Generic letters
- Unknown experts
- Too brief
- Outdated knowledge

3. Evidence
- Irrelevant materials
- Duplicate submissions
- Unverifiable claims
- Poor presentation

4. Applications
- Wrong visa type
- Missing deadlines
- Incomplete forms
- Poor planning

## Contact Information

Tech Nation:
- Email: visas@technation.io
- Website: technation.io/visa
- Guide: technation-globaltalentvisa-guide.notion.site
- Support: Available 9am-5pm UK time

## Updates and Changes

This guide is updated regularly. Always check:
- Latest version online
- Home Office updates
- Immigration rules
- Fee changes
- Process updates
"""

    def _create_chunks(self, text: str) -> List[Document]:
        """Create optimized chunks from text with metadata"""
        try:
            # Initialize text splitter with optimized parameters
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=500,
                chunk_overlap=100,
                separators=[
                    "\n## ",     # Major sections
                    "\n### ",    # Subsections
                    "\n#### ",   # Sub-subsections
                    "\n- ",      # List items
                    "\n1. ",     # Numbered items
                    "\n\n",      # Paragraphs
                    ". ",        # Sentences
                    ", ",        # Clauses
                    " ",         # Words
                    ""          # Characters
                ],
                keep_separator=True,
                add_start_index=True,
            )

            # Split text into sections
            sections = []
            current_section = ""
            current_section_title = ""

            for line in text.split('\n'):
                if line.startswith('## '):
                    if current_section:
                        sections.append((current_section_title, current_section))
                    current_section_title = line[3:].strip()
                    current_section = line + '\n'
                else:
                    current_section += line + '\n'

            if current_section:
                sections.append((current_section_title, current_section))

            # Create chunks with metadata
            chunks = []
            for section_title, section_content in sections:
                section_chunks = text_splitter.create_documents([section_content])

                for chunk in section_chunks:
                    chunk.metadata.update({
                        "section": section_title,
                        "source": "Tech Nation Guide",
                        "version": self.guide_metadata["version"],
                        "last_updated": self.guide_metadata["last_updated"]
                    })
                    chunks.append(chunk)

            logger.info(f"Created {len(chunks)} chunks from guide content")
            return chunks

        except Exception as e:
            logger.error(f"Error creating chunks: {e}")
            raise
    
    def _initialize_vector_store(self):
        """Initialize the vector store with optimized chunks"""
        try:
            # Create chunks with metadata
            chunks = self._create_chunks(self.guide_content)

            # Create vector store with enhanced parameters
            self.vector_store = FAISS.from_documents(
                documents=chunks,
                embedding=self.embeddings,
            )

            # Store section metadata for quick reference
            self.guide_metadata["sections"] = {
                chunk.metadata["section"]: {
                    "start_index": chunk.metadata["start_index"],
                    "content_length": len(chunk.page_content)
                }
                for chunk in chunks
            }

            logger.info(f"Vector store initialized successfully with {len(chunks)} chunks")

        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            raise

    def _build_prompt_template(self) -> str:
        """Build the enhanced prompt template for query responses"""
        return """
        You are a specialized AI assistant for the Tech Nation Global Talent Visa Guide, version {version} (last updated: {last_updated}).

        CONTEXT INFORMATION:
        {context}

        USER PROFILE:
        {user_context}

        QUERY: {query}

        RESPONSE GUIDELINES:

        1. ACCURACY & SOURCES
        - Use ONLY information from the provided Tech Nation Guide context
        - Quote specific sections when relevant
        - If information isn't in the guide, state: "The Tech Nation Guide doesn't specifically address this point"
        - Include section references for all key information

        2. STRUCTURE
        - Start with a direct, clear answer
        - Follow with detailed supporting information
        - End with relevant next steps or requirements
        - Use markdown formatting for clarity

        3. APPLICANT-SPECIFIC GUIDANCE
        - Tailor information to the applicant's profile
        - Specify which criteria apply (Talent vs Promise)
        - Highlight relevant technical or business requirements
        - Note any fast-track eligibility

        4. REQUIREMENTS & DEADLINES
        - Bold all mandatory requirements
        - Clearly state document limits and deadlines
        - Specify any time-sensitive information
        - List all required evidence

        5. FORMAT & CLARITY
        - Use bullet points for lists
        - Create clear section headings
        - Highlight important deadlines or requirements
        - Include relevant examples from the guide

        6. VERIFICATION & UPDATES
        - Note the guide version and last update date
        - Mention if requirements have changed recently
        - Include relevant section references
        - Link to official sources when appropriate

        Answer:
        """


    def _process_user_context(self, context: Dict[str, Any]) -> str:
        """Process user context into a structured format"""
        try:
            # Default values for missing context
            defaults = {
                'stage': 'Not specified',
                'path': 'Not specified',
                'experience_years': 'Not specified',
                'technical_background': 'Not specified',
                'current_role': 'Not specified',
                'expertise_areas': [],
                'visa_type': 'Not specified'
            }

            # Merge provided context with defaults
            context_data = {**defaults, **context} if context else defaults

            # Build structured context string
            return f"""
            Applicant Details:
            - Application Stage: {context_data['stage']}
            - Visa Path: {context_data['path']}
            - Years of Experience: {context_data['experience_years']}
            - Technical Background: {context_data['technical_background']}
            - Current Role: {context_data['current_role']}
            - Areas of Expertise: {', '.join(context_data['expertise_areas']) if context_data['expertise_areas'] else 'Not specified'}
            - Target Visa Type: {context_data['visa_type']}
            """

        except Exception as e:
            logger.error(f"Error processing user context: {e}")
            return "No specific context provided"

    def _post_process_response(self, response: str) -> str:
        """Clean and enhance the response format for better readability"""
        try:
            import re

            # Clean up excessive whitespace
            response = re.sub(r'\n{3,}', '\n\n', response)

            # Format headers properly
            response = re.sub(r'(###\s.*?)(\n[^#])', r'\1\n\n\2', response)

            # Format lists with proper spacing
            response = re.sub(r'(\n[^-\n].*?)(\n-\s)', r'\1\n\2', response)

            # Format bold text more visibly
            response = re.sub(r'\*\*(.*?)\*\*', r'**\1**', response)

            # Ensure paragraph breaks
            response = re.sub(r'(\.\s)([A-Z][^.\n]*?\:)', r'\1\n\n\2', response)

            # Format important sections
            response = re.sub(r'(Important Notes:)', r'\n\n**\1**', response)
            response = re.sub(r'(Next Steps:)', r'\n\n**\1**', response)

            # Ensure clean formatting for section headers
            sections = ["Eligibility Criteria", "Document Preparation", "Application Process",
                    "Required Documents", "Next Steps", "Important Notes"]
            for section in sections:
                response = re.sub(f'({section})', r'\n\n**\1**', response)

            # Clean footer formatting
            footer = f"""

    ---

    **Information from Tech Nation Guide:**
    - Version: {self.guide_metadata['version']}
    - Last Updated: {self.guide_metadata['last_updated']}
    - Source: {self.guide_metadata['source_url']}
    """

            # Replace existing footer with clean version
            response = re.sub(r'---\s*\*Information based on Tech Nation Guide.*', '', response, flags=re.DOTALL)
            response = response.strip() + footer

            return response

        except Exception as e:
            logger.error(f"Error in post-processing response: {e}")
            return response



    def query(self, question: str, context: Dict[str, Any]) -> str:
        """Execute a query against the Tech Nation guide with enhanced context"""
        try:
            # Get user context from the input context
            user_context = context.get('user_context', {})
            version = context.get('version', '1.0')
            last_updated = context.get('last_updated', 'Not specified')

            # Format the user context string
            user_context_str = (
                f"Applicant Profile:\n"
                f"- Application Stage: {user_context.get('stage', 'Not specified')}\n"
                f"- Visa Path: {user_context.get('path', 'Not specified')}\n"
                f"- Years of Experience: {user_context.get('experience_years', 'Not specified')}\n"
                f"- Technical Background: {'Yes' if user_context.get('technical_background') else 'No'}\n"
                f"- Business Background: {'Yes' if user_context.get('business_background') else 'No'}\n"
                f"- Areas of Expertise: {', '.join(user_context.get('expertise_areas', []))}"
            )

            # Get relevant documents
            docs = self.vector_store.similarity_search(question, k=5)
            context_text = "\n".join([doc.page_content for doc in docs])

            # Get the template string
            template_str = self._build_prompt_template()

            # Manually format the template
            prompt = template_str.replace("{context}", context_text)
            prompt = prompt.replace("{query}", question)
            prompt = prompt.replace("{user_context}", user_context_str)
            prompt = prompt.replace("{version}", version)
            prompt = prompt.replace("{last_updated}", last_updated)

            # Call the LLM directly
            response = self.llm.invoke(prompt).content

            # Post-process and return
            return self._post_process_response(response)

        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return self._generate_error_response()

    def _generate_error_response(self) -> str:
        """Generate a formatted error response"""
        return """
        ### System Notice

        I apologize, but I'm currently experiencing difficulties accessing the Tech Nation Guide database.

        **Please:**
        1. Try your question again in a few moments
        2. Verify your question is clear and specific
        3. Visit the official guide at: https://technation-globaltalentvisa-guide.notion.site/
        4. Contact support if this issue persists

        *This is a temporary technical issue and not related to your eligibility or application.*

        ---
        Error Timestamp: {timestamp}
        """.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def update_guide_content(self, new_content: str) -> bool:
        """Update the guide content and reinitialize the vector store"""
        try:
            self.guide_content = new_content
            self.guide_metadata["last_updated"] = datetime.now().strftime("%Y-%m-%d")
            self.guide_metadata["version"] = str(float(self.guide_metadata["version"]) + 0.1)

            # Reinitialize vector store with new content
            self._initialize_vector_store()

            logger.info(f"Guide content updated successfully. New version: {self.guide_metadata['version']}")
            return True

        except Exception as e:
            logger.error(f"Failed to update guide content: {e}")
            return False

# Usage example
if __name__ == "__main__":
    import os

    # Initialize RAG system
    rag = TechNationRAG(openai_api_key=os.getenv("OPENAI_API_KEY"))

    # Example query with context
    question = "What are the eligibility criteria for Exceptional Promise?"
    context = {
        "stage": "Initial Application",
        "path": "Technical",
        "experience_years": "3",
        "technical_background": "Yes",
        "current_role": "Senior Developer",
        "expertise_areas": ["AI", "Machine Learning"],
        "visa_type": "Exceptional Promise"
    }

    response = rag.query(question, context)
    print(response)