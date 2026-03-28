"""전략 조건 트리 평가기.

OHLCV DataFrame 과 조건 트리(dict)를 입력받아 지표를 계산하고,
AND/OR 트리 구조로 매수/매도 신호 조건을 평가합니다.
ta-lib 없이 pandas_ta 만 사용합니다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd
import pandas_ta as ta  # type: ignore[import]

logger = logging.getLogger(__name__)


@dataclass
class ConditionResult:
    """조건 평가 결과."""

    matched: bool
    triggered: list[str] = field(default_factory=list)


class StrategyEvaluator:
    """JSON 조건 트리를 평가해 ConditionResult 를 반환하는 서비스 클래스.

    지원 지표:
        RSI, MACD, BB (Bollinger Bands), MA (SMA), EMA,
        STOCH (Stochastic), CCI, VOLUME

    조건 트리 예시::

        {
            "operator": "AND",
            "conditions": [
                {
                    "indicator": "RSI",
                    "operator": "lt",
                    "value": 30,
                    "params": {"timeframe": "1h", "period": 14}
                },
                {
                    "indicator": "BB",
                    "operator": "price_below_lower",
                    "value": None,
                    "params": {"timeframe": "1h", "period": 20, "std": 2}
                }
            ]
        }
    """

    SUPPORTED_INDICATORS: frozenset[str] = frozenset(
        {"RSI", "MACD", "BB", "MA", "SMA", "EMA", "STOCH", "CCI", "VOLUME"}
    )

    def evaluate(
        self, condition_tree: dict, ohlcv: pd.DataFrame
    ) -> ConditionResult:
        """조건 트리 전체 평가 진입점.

        Args:
            condition_tree: 중첩 AND/OR 조건 트리 dict
            ohlcv:          OHLCV DataFrame (columns: open, high, low, close, volume)

        Returns:
            ConditionResult(matched, triggered)
        """
        indicators = self._compute_indicators(condition_tree, ohlcv)
        return self._eval_tree(condition_tree, indicators)

    # ── Tree Traversal ────────────────────────────────────────────────────────

    def _eval_tree(self, node: dict, indicators: dict) -> ConditionResult:
        """재귀적으로 AND/OR 노드를 평가합니다."""
        op = node.get("operator", "")
        if op in ("AND", "OR"):
            children = node.get("conditions", [])
            results = [self._eval_tree(c, indicators) for c in children]
            if op == "AND":
                matched = all(r.matched for r in results)
            else:
                matched = any(r.matched for r in results)
            triggered = [t for r in results for t in r.triggered]
            return ConditionResult(matched=matched, triggered=triggered)

        return self._eval_leaf(node, indicators)

    def _eval_leaf(self, cond: dict, indicators: dict) -> ConditionResult:
        """단말 조건 노드를 평가합니다."""
        ind = cond.get("indicator", "")
        tf = cond.get("params", {}).get("timeframe", "1h")
        key = f"{ind}_{tf}"
        value = indicators.get(key)

        if value is None:
            logger.debug("Indicator not available: %s", key)
            return ConditionResult(False)

        op = cond.get("operator", "")
        threshold = cond.get("value")
        close_price = indicators.get("CLOSE", 0.0)

        # 연산자 → 람다 매핑
        ops: dict = {
            # 단순 비교
            "lt":  lambda v, t: v < t,
            "gt":  lambda v, t: v > t,
            "lte": lambda v, t: v <= t,
            "gte": lambda v, t: v >= t,
            # 다른 지표 대비 배수 비교 (예: VOLUME > volume_ma_20 * 1.5)
            "gt_multiple": lambda v, t: v > indicators.get(
                cond.get("compare_to", ""), 0
            ) * t,
            # Bollinger Bands 가격 위치
            "price_below_lower": lambda v, _: close_price < v.get("lower", 0),
            "price_above_upper": lambda v, _: close_price > v.get(
                "upper", float("inf")
            ),
            # MACD 크로스
            "golden_cross": lambda v, _: v.get("cross") == "golden",
            "dead_cross":   lambda v, _: v.get("cross") == "dead",
            # MACD 방향
            "macd_positive": lambda v, _: v.get("diff", 0) > 0,
            "macd_negative": lambda v, _: v.get("diff", 0) < 0,
        }

        fn = ops.get(op)
        if fn is None:
            logger.debug("Unsupported operator: %s", op)
            return ConditionResult(False)

        try:
            matched = bool(fn(value, threshold))
        except Exception as e:
            logger.debug("Leaf eval error (ind=%s op=%s): %s", ind, op, e)
            matched = False

        label = f"{ind}({tf}) {op} {threshold}"
        return ConditionResult(
            matched=matched, triggered=[label] if matched else []
        )

    # ── Indicator Computation ─────────────────────────────────────────────────

    def _compute_indicators(
        self, tree: dict, ohlcv: pd.DataFrame
    ) -> dict:
        """트리에서 필요한 지표를 추출하고 pandas_ta 로 계산합니다."""
        needed = self._extract_needed_indicators(tree)

        close = ohlcv["close"]
        high = ohlcv["high"]
        low = ohlcv["low"]
        volume = ohlcv["volume"]

        result: dict = {"CLOSE": float(close.iloc[-1])}

        for ind, params in needed.items():
            tf = params.get("timeframe", "1h")
            try:
                if ind == "RSI":
                    period = int(params.get("period", 14))
                    rsi = ta.rsi(close, length=period)
                    result[f"RSI_{tf}"] = (
                        float(rsi.iloc[-1])
                        if rsi is not None and not rsi.empty
                        else 50.0
                    )

                elif ind == "MACD":
                    fast = int(params.get("fast", 12))
                    slow = int(params.get("slow", 26))
                    signal = int(params.get("signal", 9))
                    macd_df = ta.macd(close, fast=fast, slow=slow, signal=signal)
                    if macd_df is not None and not macd_df.empty:
                        # pandas_ta 컬럼: MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
                        # histogram 컬럼(h) 로 크로스 판단
                        hist_cols = [
                            c for c in macd_df.columns if "h" in c.lower()
                        ]
                        hist = (
                            macd_df[hist_cols[0]]
                            if hist_cols
                            else macd_df.iloc[:, 2]
                        )
                        prev = float(hist.iloc[-2]) if len(hist) > 1 else 0.0
                        curr = float(hist.iloc[-1])
                        if prev < 0 <= curr:
                            cross = "golden"
                        elif prev > 0 >= curr:
                            cross = "dead"
                        else:
                            cross = "none"
                        result[f"MACD_{tf}"] = {"diff": curr, "cross": cross}

                elif ind == "BB":
                    period = int(params.get("period", 20))
                    std = float(params.get("std", 2.0))
                    bb = ta.bbands(close, length=period, std=std)
                    if bb is not None and not bb.empty:
                        cols = list(bb.columns)
                        # pandas_ta 컬럼 순서: BBL, BBM, BBU, BBB, BBP
                        lower_col = next(
                            (c for c in cols if c.startswith("BBL")), cols[0]
                        )
                        mid_col = next(
                            (c for c in cols if c.startswith("BBM")), cols[1]
                        )
                        upper_col = next(
                            (c for c in cols if c.startswith("BBU")), cols[2]
                        )
                        result[f"BB_{tf}"] = {
                            "upper": float(bb[upper_col].iloc[-1]),
                            "mid":   float(bb[mid_col].iloc[-1]),
                            "lower": float(bb[lower_col].iloc[-1]),
                        }

                elif ind in ("MA", "SMA"):
                    period = int(params.get("period", 20))
                    ma = ta.sma(close, length=period)
                    result[f"MA_{tf}"] = (
                        float(ma.iloc[-1]) if ma is not None and not ma.empty else 0.0
                    )

                elif ind == "EMA":
                    period = int(params.get("period", 20))
                    ema = ta.ema(close, length=period)
                    result[f"EMA_{tf}"] = (
                        float(ema.iloc[-1]) if ema is not None and not ema.empty else 0.0
                    )

                elif ind == "STOCH":
                    k = int(params.get("k", 14))
                    d = int(params.get("d", 3))
                    smooth_k = int(params.get("smooth_k", 3))
                    stoch = ta.stoch(high, low, close, k=k, d=d, smooth_k=smooth_k)
                    if stoch is not None and not stoch.empty:
                        # 첫 번째 컬럼이 %K
                        result[f"STOCH_{tf}"] = float(stoch.iloc[-1, 0])

                elif ind == "CCI":
                    period = int(params.get("period", 20))
                    cci = ta.cci(high, low, close, length=period)
                    result[f"CCI_{tf}"] = (
                        float(cci.iloc[-1]) if cci is not None and not cci.empty else 0.0
                    )

                elif ind == "VOLUME":
                    result[f"VOLUME_{tf}"] = float(volume.iloc[-1])
                    vol_ma = ta.sma(volume, length=20)
                    result["volume_ma_20"] = (
                        float(vol_ma.iloc[-1])
                        if vol_ma is not None and not vol_ma.empty
                        else 0.0
                    )

            except Exception as e:
                # 지표 계산 실패 시 해당 조건은 False 처리 (트레이딩 중단 없음)
                logger.warning("Indicator compute error (ind=%s tf=%s): %s", ind, tf, e)

        return result

    def _extract_needed_indicators(self, node: dict) -> dict[str, dict]:
        """트리를 순회하며 필요한 지표와 파라미터를 수집합니다."""
        needed: dict[str, dict] = {}
        if "indicator" in node:
            ind = node["indicator"]
            if ind in self.SUPPORTED_INDICATORS:
                # 같은 지표의 파라미터가 여러 번 등장하면 마지막 것을 사용
                needed[ind] = node.get("params", {})
        for child in node.get("conditions", []):
            needed.update(self._extract_needed_indicators(child))
        return needed
