# tech_nation_knowledge_base.py
import re
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class TechNationKnowledgeBase:
    """Rule-based knowledge base for Tech Nation Global Talent Visa queries"""

    def __init__(self):
        """Initialize the knowledge base with predefined responses"""
        self.responses = self._load_responses()
        self.keywords = self._generate_keywords()
        logger.info("TechNation Knowledge Base initialized")

    def _load_responses(self) -> Dict[str, Dict[str, str]]:
        """Load predefined responses for common Tech Nation visa questions"""
        return {
            "eligibility": {
                "response": """
## Eligibility Criteria

There are two paths for eligibility:

### 1. Exceptional Talent
- For established leaders in digital technology
- Must meet at least 2 of 4 qualifying criteria
- Significant achievements in the last 5 years

### 2. Exceptional Promise
- For emerging leaders in digital technology
- Must meet at least 2 of 4 qualifying criteria
- Achievements showing potential in the last 5 years

**Technical applicants** should demonstrate technical expertise in areas like software engineering, AI/ML, data science, etc.

**Business applicants** should demonstrate commercial/business expertise in areas like scaling businesses, product management, or investment.
                """,
                "section": "Eligibility"
            },
            # All your other responses here
        }
        # Include all your other responses from the original code

    def _generate_keywords(self) -> Dict[str, str]:
        """Generate keyword mappings to responses"""
        return {
            # Eligibility keywords
            "eligibility": "eligibility",
            "qualify": "eligibility",
            "eligible": "eligibility",
            # All your other keywords here
        }
        # Include all your other keywords from the original code

    def get_response(self, query: str) -> str:
        """Get the most relevant response based on keywords and patterns in the query"""
        query = query.lower()

        # Check for greetings or empty queries
        if self._is_greeting(query) or not query.strip():
            return self.responses["welcome"]["response"]

        # Check for specific patterns first
        if re.search(r'(how|what).*personal statement', query):
            return self.responses["personal_statement"]["response"]

        # All your other pattern matching logic here
        # Include all your other pattern matching from the original code

        # Count keyword matches for each response category
        matches = {}
        for keyword, response_key in self.keywords.items():
            if keyword in query:
                matches[response_key] = matches.get(response_key, 0) + 1

        # If no matches, return default response
        if not matches:
            return self._get_default_response(query)

        # Get the response key with the most matches
        best_match = max(matches.items(), key=lambda x: x[1])[0]
        return self.responses[best_match]["response"]

    def _is_greeting(self, query: str) -> bool:
        """Check if the query is a greeting"""
        greetings = ["hello", "hi", "hey", "greetings", "good morning", "good afternoon",
                    "good evening", "howdy", "what's up", "hiya"]
        return any(greeting in query for greeting in greetings) or len(query) < 5

    def _get_default_response(self, query: str) -> str:
        """Generate a default response when no keywords match"""
        # Check for common question patterns
        if re.search(r'^(what|how|can|do|is|are|when|where|why|which)', query.lower()):
            return """
I don't have specific information about that in my Tech Nation visa guide.

Here are some topics I can help with:
- Eligibility criteria for Exceptional Talent or Promise
- Required documents (personal statement, CV, recommendation letters)
- Application process and timeline
- Fees and processing times
- Technical and business skills requirements
- Family members and settlement options

Please ask about one of these topics or rephrase your question.
            """

        # For non-questions, provide a more general response
        return """
I'm a specialized knowledge base for the Tech Nation Global Talent Visa. I can answer questions about:

- Eligibility criteria
- Application process
- Required documents
- Timeline and fees
- Technical and business skills
- Family members and settlement

How can I help you with your Tech Nation visa application?
        """