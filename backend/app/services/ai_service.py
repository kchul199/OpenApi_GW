"""AI 자문 서비스 – Claude API 를 통한 매매 신호 자문."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.ai_consultation import AIConsultation

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """You are an expert cryptocurrency trading advisor.
Analyze the following trading signal and market context, then provide a recommendation.

Strategy: {strategy_name}
Symbol: {symbol}
Timeframe: {timeframe}
Signal: {signal}
Triggered Conditions: {triggered_conditions}
Current Price: {current_price} USDT
Market Context: {market_context}

Respond in JSON with this exact schema:
{{
  "recommendation": "execute" | "hold" | "cancel",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<brief explanation>"
}}
"""


class AIService:
    """Claude API 를 사용하는 AI 자문 서비스."""

    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
        return self._client

    async def consult(
        self,
        db: AsyncSession,
        *,
        strategy_id: uuid.UUID,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        signal: str,
        triggered_conditions: list[str],
        current_price: float,
        market_context: dict,
    ) -> dict:
        """AI 자문을 요청하고 AIConsultation 레코드를 저장합니다.

        Returns:
            {"recommendation": str, "confidence": float, "reasoning": str}
        """
        prompt = _PROMPT_TEMPLATE.format(
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            triggered_conditions=", ".join(triggered_conditions),
            current_price=current_price,
            market_context=str(market_context),
        )

        recommendation = "hold"
        confidence = 0.5
        reasoning = "AI consultation unavailable"
        raw_response = ""
        error = None

        try:
            import asyncio
            response = await asyncio.wait_for(
                self.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=256,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=settings.AI_CONSULT_TIMEOUT_SECONDS,
            )
            raw_response = response.content[0].text if response.content else ""
            import json
            parsed = json.loads(raw_response)
            recommendation = parsed.get("recommendation", "hold")
            confidence = float(parsed.get("confidence", 0.5))
            reasoning = parsed.get("reasoning", "")
        except asyncio.TimeoutError:
            error = "AI consultation timeout"
            logger.warning("AI consultation timed out for strategy=%s", strategy_id)
        except Exception as exc:
            error = str(exc)
            logger.error("AI consultation error: %s", exc)

        # DB 저장
        record = AIConsultation(
            id=uuid.uuid4(),
            strategy_id=strategy_id,
            prompt_version=settings.AI_CONSULT_PROMPT_VERSION,
            input_context={
                "signal": signal,
                "triggered_conditions": triggered_conditions,
                "current_price": current_price,
                "market_context": market_context,
            },
            recommendation=recommendation,
            confidence_score=confidence,
            reasoning=reasoning,
            raw_response=raw_response,
            is_error=error is not None,
            error_message=error,
        )
        db.add(record)
        await db.flush()

        return {
            "recommendation": recommendation,
            "confidence": confidence,
            "reasoning": reasoning,
        }
