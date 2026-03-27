-- =============================================================================
-- 코인 자동 매매 시스템 - PostgreSQL 초기화 DDL
-- =============================================================================
-- 이 파일은 docker-entrypoint-initdb.d/ 에 마운트되어
-- 컨테이너 최초 기동 시 자동 실행됩니다.
--
-- 테이블 목록:
--   1.  users                  - 사용자 계정
--   2.  jwt_blacklist           - 무효화된 JWT 토큰
--   3.  exchange_accounts       - 거래소 API 계정 (암호화)
--   4.  balances                - 거래소별 자산 잔고
--   5.  strategies              - 자동매매 전략 정의
--   6.  orders                  - 주문 내역
--   7.  ai_consultations        - AI 의사결정 기록
--   8.  candles                 - OHLCV 캔들 데이터
--   9.  portfolio               - 포트폴리오 현황
--   10. strategy_conflicts      - 전략 충돌 기록
--   11. emergency_stops         - 긴급 정지 이력
--   12. backtest_results        - 백테스트 결과
-- =============================================================================

-- pgcrypto: gen_random_uuid(), crypt() 등 암호화 함수 활성화
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- 1. users - 사용자 계정
-- =============================================================================
CREATE TABLE users (
    -- UUID v4 기본 키 (노출 안전, 예측 불가)
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    -- 로그인 이메일 (고유)
    email             VARCHAR(255) UNIQUE NOT NULL,
    -- bcrypt 등 해시된 비밀번호
    password_hash     VARCHAR(255) NOT NULL,
    -- TOTP 2FA 시크릿 (Base32 인코딩, 선택)
    totp_secret       VARCHAR(64),
    -- 계정 활성화 여부 (비활성화 = 소프트 삭제)
    is_active         BOOLEAN      DEFAULT true,
    created_at        TIMESTAMPTZ  DEFAULT now(),
    updated_at        TIMESTAMPTZ  DEFAULT now()
);

COMMENT ON TABLE  users                IS '사용자 계정';
COMMENT ON COLUMN users.totp_secret    IS 'TOTP 2FA 시크릿 (Base32). NULL이면 2FA 미설정';
COMMENT ON COLUMN users.is_active      IS 'false = 소프트 삭제 / 계정 정지';

-- =============================================================================
-- 2. jwt_blacklist - 로그아웃 / 토큰 무효화 목록
-- =============================================================================
CREATE TABLE jwt_blacklist (
    -- JWT jti (JWT ID) 클레임 값
    jti               UUID         PRIMARY KEY,
    -- 토큰 발급 대상 사용자
    user_id           UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- 블랙리스트 등록 사유 (logout, password_change, revoked 등)
    reason            VARCHAR(100),
    -- 원 토큰 만료 시각 (이후 레코드 자동 정리 가능)
    expires_at        TIMESTAMPTZ  NOT NULL,
    created_at        TIMESTAMPTZ  DEFAULT now()
);

-- 만료된 레코드 일괄 삭제 쿼리 성능을 위한 인덱스
CREATE INDEX idx_jwt_blacklist_expires ON jwt_blacklist(expires_at);

COMMENT ON TABLE  jwt_blacklist            IS '무효화된 JWT 토큰 블랙리스트';
COMMENT ON COLUMN jwt_blacklist.expires_at IS '만료 후 주기적 purge 처리용';

-- =============================================================================
-- 3. exchange_accounts - 거래소 API 계정 (API 키는 암호화 저장)
-- =============================================================================
CREATE TABLE exchange_accounts (
    id                    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- 지원 거래소 식별자
    exchange_id           VARCHAR(20)  NOT NULL CHECK (exchange_id IN ('binance', 'upbit', 'bithumb')),
    -- AES-256-GCM 암호화된 API Key (BYTEA)
    api_key_encrypted     BYTEA        NOT NULL,
    -- AES-256-GCM 암호화된 API Secret (BYTEA)
    api_secret_encrypted  BYTEA        NOT NULL,
    -- 테스트넷 여부 (true: 테스트넷, false: 실거래)
    is_testnet            BOOLEAN      DEFAULT true,
    is_active             BOOLEAN      DEFAULT true,
    created_at            TIMESTAMPTZ  DEFAULT now()
);

COMMENT ON TABLE  exchange_accounts                     IS '거래소 API 계정';
COMMENT ON COLUMN exchange_accounts.api_key_encrypted   IS 'AES-256-GCM 암호화. 복호화는 애플리케이션 레이어에서 처리';
COMMENT ON COLUMN exchange_accounts.api_secret_encrypted IS 'AES-256-GCM 암호화';
COMMENT ON COLUMN exchange_accounts.is_testnet          IS 'true=테스트넷(기본), false=실거래 주의';

-- =============================================================================
-- 4. balances - 거래소별 자산 잔고 (실시간 동기화)
-- =============================================================================
CREATE TABLE balances (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exchange_id VARCHAR(20)  NOT NULL,
    -- 자산 심볼 (예: BTC, USDT, KRW)
    symbol      VARCHAR(20)  NOT NULL,
    -- 사용 가능 잔고
    available   NUMERIC(28, 8) NOT NULL,
    -- 주문 잠금 잔고
    locked      NUMERIC(28, 8) NOT NULL DEFAULT 0,
    -- 마지막 동기화 시각
    synced_at   TIMESTAMPTZ  NOT NULL,
    -- (user, exchange, symbol) 조합은 유일
    UNIQUE (user_id, exchange_id, symbol)
);

COMMENT ON TABLE  balances           IS '거래소별 실시간 자산 잔고';
COMMENT ON COLUMN balances.locked    IS '미체결 주문으로 잠긴 수량';
COMMENT ON COLUMN balances.synced_at IS '마지막으로 거래소 API에서 동기화된 시각';

-- =============================================================================
-- 5. strategies - 자동매매 전략 정의
-- =============================================================================
CREATE TABLE strategies (
    id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- 전략 이름 (사용자 정의)
    name                 VARCHAR(100) NOT NULL,
    -- 매매 심볼 (예: BTC/USDT)
    symbol               VARCHAR(20)  NOT NULL,
    -- 캔들 타임프레임 (예: 1m, 5m, 1h, 1d)
    timeframe            VARCHAR(10)  NOT NULL,
    -- 진입/청산 조건 트리 (JSON 트리 구조)
    condition_tree       JSONB        NOT NULL,
    -- 주문 설정 (수량, 레버리지, 리스크 등)
    order_config         JSONB        NOT NULL,
    -- AI 모드: off(비활성) | auto(자동실행) | semi_auto(승인 후 실행) | observe(관찰만)
    ai_mode              VARCHAR(20)  DEFAULT 'off' CHECK (ai_mode IN ('off', 'auto', 'semi_auto', 'observe')),
    -- 전략 우선순위 (1=최저 ~ 10=최고, 충돌 해결에 사용)
    priority             SMALLINT     DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),
    -- HOLD 결정 후 재시도 간격 (초)
    hold_retry_interval  INTEGER      DEFAULT 300,
    -- HOLD 최대 재시도 횟수
    hold_max_retry       SMALLINT     DEFAULT 3,
    -- 전략 활성화 여부
    is_active            BOOLEAN      DEFAULT false,
    created_at           TIMESTAMPTZ  DEFAULT now(),
    updated_at           TIMESTAMPTZ  DEFAULT now()
);

-- 사용자별 활성 전략 조회 (전략 엔진 메인 쿼리)
CREATE INDEX idx_strategies_user_active ON strategies(user_id, is_active);
-- 심볼별 전략 조회 (캔들 수신 시 라우팅)
CREATE INDEX idx_strategies_symbol ON strategies(symbol);

COMMENT ON TABLE  strategies                    IS '자동매매 전략 정의';
COMMENT ON COLUMN strategies.condition_tree     IS 'JSON 트리: {operator, conditions:[]} 재귀 구조';
COMMENT ON COLUMN strategies.order_config       IS '주문 파라미터: 수량타입, 비율, 레버리지, SL/TP 등';
COMMENT ON COLUMN strategies.ai_mode            IS 'off: AI 미사용 | auto: 자동 실행 | semi_auto: 사용자 승인 필요 | observe: 로깅만';
COMMENT ON COLUMN strategies.priority           IS '1(낮음)~10(높음). 동일 심볼 충돌 시 높은 우선순위 전략 우선';

-- =============================================================================
-- 6. orders - 주문 내역
-- =============================================================================
CREATE TABLE orders (
    id                 UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    -- 연관 전략 (수동 주문 시 NULL 허용)
    strategy_id        UUID          REFERENCES strategies(id) ON DELETE SET NULL,
    exchange_id        VARCHAR(20)   NOT NULL,
    -- 거래소 발급 주문 ID
    exchange_order_id  VARCHAR(100),
    symbol             VARCHAR(20)   NOT NULL,
    -- 매수/매도
    side               VARCHAR(4)    NOT NULL CHECK (side IN ('buy', 'sell')),
    -- market, limit, stop_limit, stop_market 등
    order_type         VARCHAR(20)   NOT NULL,
    -- 지정가 (시장가는 NULL)
    price              NUMERIC(28, 8),
    -- 주문 수량
    quantity           NUMERIC(28, 8) NOT NULL,
    -- 체결된 수량
    filled_quantity    NUMERIC(28, 8) DEFAULT 0,
    -- 평균 체결 가격
    avg_fill_price     NUMERIC(28, 8),
    -- 수수료 (Quote 기준)
    fee                NUMERIC(28, 8) DEFAULT 0,
    -- 슬리피지 비율 (%)
    slippage_pct       NUMERIC(10, 6),
    -- 주문 상태
    status             VARCHAR(20)   NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'open', 'filled', 'partially_filled', 'cancelled', 'rejected')),
    created_at         TIMESTAMPTZ   DEFAULT now(),
    -- 체결 완료 시각
    filled_at          TIMESTAMPTZ,
    updated_at         TIMESTAMPTZ   DEFAULT now()
);

-- 전략별 미체결/체결 주문 조회
CREATE INDEX idx_orders_strategy_status ON orders(strategy_id, status);
-- 최신 주문 내역 페이징
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);

COMMENT ON TABLE  orders                    IS '주문 생성부터 체결/취소까지의 전체 주문 이력';
COMMENT ON COLUMN orders.slippage_pct       IS '(avg_fill_price - price) / price * 100. 음수 = 유리한 슬리피지';
COMMENT ON COLUMN orders.exchange_order_id  IS '거래소 응답의 orderId. NULL = 아직 거래소 제출 전';

-- =============================================================================
-- 7. ai_consultations - AI 의사결정 기록
-- =============================================================================
CREATE TABLE ai_consultations (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id      UUID         NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    -- 연관 주문 (HOLD/AVOID 시 NULL)
    order_id         UUID         REFERENCES orders(id) ON DELETE SET NULL,
    -- 사용된 AI 모델명 (예: claude-3-5-sonnet-20241022)
    model            VARCHAR(50)  NOT NULL,
    -- 프롬프트 버전 (A/B 테스트, 버전 관리)
    prompt_version   SMALLINT     NOT NULL DEFAULT 1,
    -- AI 최종 결정
    decision         VARCHAR(10)  NOT NULL CHECK (decision IN ('execute', 'hold', 'avoid')),
    -- 신뢰도 점수 (0~100)
    confidence       SMALLINT     CHECK (confidence BETWEEN 0 AND 100),
    -- 결정 이유 (텍스트)
    reason           TEXT,
    -- 위험도 평가
    risk_level       VARCHAR(10)  CHECK (risk_level IN ('low', 'medium', 'high')),
    -- 주요 우려사항 목록 (JSON 배열)
    key_concerns     JSONB,
    -- semi_auto 모드: 사용자 승인 여부 (NULL = 대기 중)
    user_approved    BOOLEAN,
    -- AI API 응답 지연 (ms)
    latency_ms       INTEGER,
    created_at       TIMESTAMPTZ  DEFAULT now()
);

-- 전략별 AI 결정 이력 최신순 조회
CREATE INDEX idx_ai_consultations_strategy ON ai_consultations(strategy_id, created_at DESC);
-- 결정 유형별 분석
CREATE INDEX idx_ai_consultations_decision ON ai_consultations(decision);

COMMENT ON TABLE  ai_consultations              IS 'AI(Claude) 매매 의사결정 요청 및 응답 전체 이력';
COMMENT ON COLUMN ai_consultations.user_approved IS 'semi_auto 모드 전용. NULL=대기, true=승인, false=거절';
COMMENT ON COLUMN ai_consultations.key_concerns  IS '예: ["high_volatility", "low_volume", "bearish_divergence"]';

-- =============================================================================
-- 8. candles - OHLCV 캔들 데이터
-- =============================================================================
CREATE TABLE candles (
    symbol    VARCHAR(20)    NOT NULL,
    exchange  VARCHAR(20)    NOT NULL,
    timeframe VARCHAR(10)    NOT NULL,
    -- 캔들 시작 시각 (UTC)
    ts        TIMESTAMPTZ    NOT NULL,
    -- OHLCV
    open      NUMERIC(28, 8) NOT NULL,
    high      NUMERIC(28, 8) NOT NULL,
    low       NUMERIC(28, 8) NOT NULL,
    close     NUMERIC(28, 8) NOT NULL,
    volume    NUMERIC(28, 8) NOT NULL,
    -- 복합 기본키: (심볼, 거래소, 타임프레임, 시각)
    PRIMARY KEY (symbol, exchange, timeframe, ts)
);

-- 최근 N개 캔들 조회 (기술적 지표 계산용)
CREATE INDEX idx_candles_recent ON candles(symbol, exchange, timeframe, ts DESC);

COMMENT ON TABLE  candles IS 'OHLCV 캔들 데이터. 타임시리즈 특성상 TimescaleDB 하이퍼테이블로 전환 가능';
COMMENT ON COLUMN candles.ts IS '캔들 시작 시각 (UTC). 종료 시각 = ts + timeframe interval';

-- =============================================================================
-- 9. portfolio - 포트폴리오 현황 (보유 자산별 평단가)
-- =============================================================================
CREATE TABLE portfolio (
    id               UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol           VARCHAR(20)   NOT NULL,
    exchange_id      VARCHAR(20)   NOT NULL,
    -- 보유 수량
    quantity         NUMERIC(28, 8) NOT NULL DEFAULT 0,
    -- 평균 매수 단가
    avg_buy_price    NUMERIC(28, 8),
    -- 해당 포지션 최초 투입 자본
    initial_capital  NUMERIC(28, 8),
    last_updated     TIMESTAMPTZ   DEFAULT now(),
    -- (사용자, 심볼, 거래소) 조합 유일
    UNIQUE (user_id, symbol, exchange_id)
);

COMMENT ON TABLE  portfolio                IS '현재 보유 자산 현황 및 평단가';
COMMENT ON COLUMN portfolio.avg_buy_price  IS '매수 주문 체결 시 가중 평균으로 업데이트';
COMMENT ON COLUMN portfolio.initial_capital IS '포지션 진입 시 투입한 최초 자본 (수익률 계산용)';

-- =============================================================================
-- 10. strategy_conflicts - 동일 심볼 전략 충돌 기록
-- =============================================================================
CREATE TABLE strategy_conflicts (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    -- 충돌 발생 심볼
    symbol              VARCHAR(20)  NOT NULL,
    -- 충돌에 관여한 전략 ID 목록 (JSON 배열)
    strategy_ids        JSONB        NOT NULL,
    -- 충돌 유형 (예: opposing_signals, same_direction_overload)
    conflict_type       VARCHAR(30)  NOT NULL,
    -- 해결 방법 (priority, first_come, cancel_all 등)
    resolution          VARCHAR(20),
    -- 충돌 해결 후 실행된 전략
    winner_strategy_id  UUID         REFERENCES strategies(id) ON DELETE SET NULL,
    occurred_at         TIMESTAMPTZ  DEFAULT now()
);

COMMENT ON TABLE  strategy_conflicts              IS '동일 심볼에 대해 방향이 상충하는 전략 신호 충돌 기록';
COMMENT ON COLUMN strategy_conflicts.strategy_ids IS '예: ["uuid-a", "uuid-b"]';
COMMENT ON COLUMN strategy_conflicts.conflict_type IS 'opposing_signals: 매수/매도 동시 신호 | same_direction_overload: 동방향 과다 주문';

-- =============================================================================
-- 11. emergency_stops - 긴급 정지 이력
-- =============================================================================
CREATE TABLE emergency_stops (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    -- 특정 전략 긴급정지 (NULL = 전체 정지)
    strategy_id       UUID         REFERENCES strategies(id) ON DELETE SET NULL,
    user_id           UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- 긴급 정지 사유
    reason            TEXT,
    -- 취소된 주문 ID 목록 (JSON 배열)
    cancelled_orders  JSONB,
    created_at        TIMESTAMPTZ  DEFAULT now()
);

COMMENT ON TABLE  emergency_stops                  IS '사용자 또는 시스템에 의한 긴급 매매 정지 이력';
COMMENT ON COLUMN emergency_stops.strategy_id      IS 'NULL이면 해당 사용자의 모든 전략 긴급 정지';
COMMENT ON COLUMN emergency_stops.cancelled_orders IS '정지 시 취소된 주문 UUID 배열';

-- =============================================================================
-- 12. backtest_results - 전략 백테스트 결과
-- =============================================================================
CREATE TABLE backtest_results (
    id                  UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id         UUID           NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    -- 백테스트 기간
    start_date          DATE           NOT NULL,
    end_date            DATE           NOT NULL,
    -- 백테스트 시점의 전략 파라미터 스냅샷 (변경 추적용)
    params_snapshot     JSONB          NOT NULL,
    -- 초기 자본
    initial_capital     NUMERIC(28, 8) NOT NULL,
    -- 최종 자본
    final_capital       NUMERIC(28, 8),
    -- 총 수익률 (%)
    total_return_pct    NUMERIC(10, 4),
    -- 최대 낙폭 (MDD, %)
    max_drawdown_pct    NUMERIC(10, 4),
    -- 샤프 지수
    sharpe_ratio        NUMERIC(10, 4),
    -- 승률 (0.0000 ~ 1.0000)
    win_rate            NUMERIC(5, 4),
    -- 손익비 (Profit Factor)
    profit_factor       NUMERIC(10, 4),
    -- 총 트레이드 횟수
    total_trades        INTEGER,
    -- AI 활성화 시 수익률 (비교 분석용)
    ai_on_return_pct    NUMERIC(10, 4),
    -- AI 비활성화 시 수익률 (비교 분석용)
    ai_off_return_pct   NUMERIC(10, 4),
    -- 수수료율 (%)
    commission_pct      NUMERIC(6, 4),
    -- 슬리피지율 (%)
    slippage_pct        NUMERIC(6, 4),
    -- 자본 곡선 (시계열 JSON 배열)
    equity_curve        JSONB,
    -- 개별 트레이드 이력 (JSON 배열)
    trade_history       JSONB,
    created_at          TIMESTAMPTZ    DEFAULT now()
);

-- 전략별 최신 백테스트 결과 조회
CREATE INDEX idx_backtest_strategy ON backtest_results(strategy_id, created_at DESC);

COMMENT ON TABLE  backtest_results                IS '전략 백테스트 수행 결과 및 성과 지표';
COMMENT ON COLUMN backtest_results.params_snapshot IS '백테스트 시점의 condition_tree + order_config 스냅샷 (재현 가능성 보장)';
COMMENT ON COLUMN backtest_results.equity_curve    IS '[{"ts": "2024-01-01", "value": 10500.0}, ...] 형식';
COMMENT ON COLUMN backtest_results.trade_history   IS '[{"entry_ts": ..., "exit_ts": ..., "pnl": ..., "side": "buy"}, ...] 형식';
COMMENT ON COLUMN backtest_results.ai_on_return_pct  IS 'AI 의사결정 활성화 시나리오 수익률 (A/B 비교)';
COMMENT ON COLUMN backtest_results.ai_off_return_pct IS 'AI 의사결정 비활성화 시나리오 수익률 (A/B 비교)';

-- =============================================================================
-- 공통 updated_at 자동 갱신 트리거 함수
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- users 테이블 updated_at 자동 갱신
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- strategies 테이블 updated_at 자동 갱신
CREATE TRIGGER trg_strategies_updated_at
    BEFORE UPDATE ON strategies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- orders 테이블 updated_at 자동 갱신
CREATE TRIGGER trg_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
