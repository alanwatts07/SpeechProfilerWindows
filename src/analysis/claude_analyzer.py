"""Claude API integration for deeper personality analysis."""

import json
import logging
from typing import Optional, Dict
from datetime import datetime

from ..config import config
from ..storage.database import get_db
from ..storage.models import Speaker, AnalysisHistory

logger = logging.getLogger(__name__)


class ClaudeAnalyzer:
    """Analyzes speaker text using Claude API for deeper insights."""

    def __init__(self):
        """Initialize Claude analyzer."""
        self.api_key = config.ANTHROPIC_API_KEY
        self._client = None

    def _get_client(self):
        """Lazy load Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "anthropic package not installed. Run: pip install anthropic"
                )
        return self._client

    def analyze(
        self,
        speaker_name: str,
        text: str,
        deception_context: str = "",
        save_to_db: bool = True,
        speaker_db_id: Optional[int] = None
    ) -> Optional[Dict]:
        """Analyze text using Claude for personality insights.

        Args:
            speaker_name: Name of the speaker
            text: Text to analyze
            deception_context: Additional context about deception markers
            save_to_db: Whether to save analysis to database
            speaker_db_id: Database ID of speaker (for saving)

        Returns:
            Dictionary with analysis insights, or None on failure
        """
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set in config")
            return None

        try:
            client = self._get_client()

            prompt = f"""Analyze this person's speech patterns and provide insights about their personality, communication style, and DECEPTION MARKERS.

Speaker: {speaker_name}
Text sample ({len(text.split())} words):
"{text}"
{deception_context}

DECEPTION PATTERNS TO LOOK FOR:
1. FALSE EMPATHY - Rich/powerful people saying "I feel your pain", "you're not alone", "I know how hard it is" (performative concern)
2. FALSE RELATABILITY - "working families", "kitchen table", "putting food on the table" (millionaires pretending to be regular folks)
3. BLAME SHIFTING - Mentioning other politicians/parties to deflect ("under [opponent]", "the previous administration")
4. HEDGING - "I believe", "to my knowledge", "I don't recall" (avoiding commitment)
5. NON-ANSWERS - "That's a great question", "Let me be clear" then not being clear
6. WEASEL WORDS - "Some people say", "Many believe", "Studies show" (vague attribution)
7. STATS AS MANIPULATION - Cherry-picked statistics to seem authoritative
8. FAKE NICENESS - "With all due respect", "My good friend" (saccharine politeness)
9. FUTURE FAKING - "We're looking into it", "Very soon" (vague promises)
10. EMOTIONAL MANIPULATION - "Think of the children", "Our freedom" (appeals over substance)

Based on this speech sample, provide a JSON response with:
{{
    "personality_summary": "2-3 sentence summary of their personality",
    "communication_style": "direct/indirect, formal/casual, etc.",
    "likely_values": ["3-5", "core", "values"],
    "how_to_persuade": "Best approach to influence this person",
    "rapport_tip": "One specific tip to build rapport right now",
    "honesty_assessment": "honest/evasive/manipulative - BE HARSH, call out BS",
    "deception_detected": ["list", "specific", "deception", "patterns", "found"],
    "specific_red_flags": "Quote specific phrases that are manipulative or deceptive"
}}

BE CRITICAL. If this sounds like a politician pandering, SAY SO. If they're using false empathy or relatability, CALL IT OUT.

Respond ONLY with the JSON object, no other text."""

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text.strip()

            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            insights = json.loads(response_text)
            logger.info(f"Claude analysis complete for {speaker_name}")

            # Save to database if requested
            if save_to_db and speaker_db_id:
                self._save_analysis(speaker_db_id, len(text.split()), insights)

            return insights

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response: {e}")
            return None
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return None

    def _save_analysis(self, speaker_db_id: int, word_count: int, insights: Dict):
        """Save analysis to database.

        Args:
            speaker_db_id: Speaker's database ID
            word_count: Word count at time of analysis
            insights: Analysis insights dictionary
        """
        try:
            db = get_db()
            with db.get_session() as session:
                analysis = AnalysisHistory(
                    speaker_db_id=speaker_db_id,
                    timestamp=datetime.utcnow(),
                    word_count_at_analysis=word_count,
                    insights_json=json.dumps(insights)
                )
                session.add(analysis)
            logger.debug(f"Saved analysis for speaker {speaker_db_id}")
        except Exception as e:
            logger.error(f"Failed to save analysis: {e}")

    def get_analysis_history(self, speaker_db_id: int) -> list:
        """Get all historical analyses for a speaker.

        Args:
            speaker_db_id: Speaker's database ID

        Returns:
            List of (timestamp, word_count, insights) tuples
        """
        try:
            db = get_db()
            with db.get_session() as session:
                analyses = (
                    session.query(AnalysisHistory)
                    .filter_by(speaker_db_id=speaker_db_id)
                    .order_by(AnalysisHistory.timestamp.desc())
                    .all()
                )

                result = []
                for analysis in analyses:
                    try:
                        insights = json.loads(analysis.insights_json) if analysis.insights_json else {}
                    except json.JSONDecodeError:
                        insights = {}

                    result.append({
                        'timestamp': analysis.timestamp,
                        'word_count': analysis.word_count_at_analysis,
                        'insights': insights
                    })

                return result
        except Exception as e:
            logger.error(f"Failed to get analysis history: {e}")
            return []

    def should_analyze(
        self,
        word_count: int,
        last_analyzed_word_count: int
    ) -> bool:
        """Check if analysis should be triggered based on word count.

        Args:
            word_count: Current word count
            last_analyzed_word_count: Word count at last analysis (0 if never)

        Returns:
            True if analysis should be triggered
        """
        threshold = config.CLAUDE_ANALYSIS_THRESHOLD
        interval = config.CLAUDE_REANALYSIS_INTERVAL

        # First analysis at threshold
        if last_analyzed_word_count == 0 and word_count >= threshold:
            return True

        # Re-analyze every interval words
        if last_analyzed_word_count > 0 and (word_count - last_analyzed_word_count) >= interval:
            return True

        return False


# Communication tips based on profile
VAK_TIPS = {
    "visual": [
        "Use words like: see, look, picture, imagine, view",
        "Show diagrams, charts, or written info",
        "Say: 'Let me show you...' or 'Picture this...'",
    ],
    "auditory": [
        "Use words like: hear, sounds, listen, tell, discuss",
        "Explain things verbally, use tone variety",
        "Say: 'How does that sound?' or 'Let me tell you...'",
    ],
    "kinesthetic": [
        "Use words like: feel, touch, grasp, handle, concrete",
        "Let them try things hands-on",
        "Say: 'How do you feel about...' or 'Let's walk through...'",
    ],
}

NEED_TIPS = {
    "significance": [
        "Acknowledge their achievements",
        "Ask about their unique contributions",
        "Highlight how they stand out",
    ],
    "approval": [
        "Give genuine compliments",
        "Show appreciation for their efforts",
        "Be supportive and encouraging",
    ],
    "acceptance": [
        "Emphasize group belonging",
        "Use inclusive language (we, us, together)",
        "Make them feel part of the team",
    ],
    "intelligence": [
        "Respect their expertise",
        "Ask for their analysis/opinion",
        "Present logical arguments",
    ],
    "power": [
        "Give them choices and control",
        "Ask what they want to do",
        "Let them lead when possible",
    ],
    "pity": [
        "Show empathy and understanding",
        "Acknowledge their struggles",
        "Offer support without judgment",
    ],
}


def get_vak_tip(vak: str) -> str:
    """Get a communication tip for a VAK modality."""
    tips = VAK_TIPS.get(vak, [])
    return tips[0] if tips else ""


def get_need_tip(need: str) -> str:
    """Get a communication tip for a social need."""
    tips = NEED_TIPS.get(need, [])
    return tips[0] if tips else ""
