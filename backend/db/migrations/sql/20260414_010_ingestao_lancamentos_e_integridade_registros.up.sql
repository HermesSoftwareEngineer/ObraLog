CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'registros'
          AND column_name = 'pista'
    ) THEN
        UPDATE registros
        SET lado_pista = pista
        WHERE lado_pista IS NULL
          AND pista IS NOT NULL;

        ALTER TABLE registros DROP COLUMN pista;
    END IF;
END $$;

ALTER TABLE registros ADD COLUMN IF NOT EXISTS raw_text TEXT;
ALTER TABLE registros ADD COLUMN IF NOT EXISTS source_message_id UUID;
ALTER TABLE registros ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE registros DROP CONSTRAINT IF EXISTS ck_registros_required_fields;
ALTER TABLE registros
ADD CONSTRAINT ck_registros_required_fields
CHECK (
    data IS NOT NULL
    AND frente_servico_id IS NOT NULL
    AND usuario_registrador_id IS NOT NULL
    AND estaca_inicial IS NOT NULL
    AND estaca_final IS NOT NULL
    AND resultado IS NOT NULL
    AND tempo_manha IS NOT NULL
    AND tempo_tarde IS NOT NULL
) NOT VALID;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'registros_usuario_registrador_id_fkey'
    ) THEN
        ALTER TABLE registros DROP CONSTRAINT registros_usuario_registrador_id_fkey;
    END IF;

    ALTER TABLE registros
    ADD CONSTRAINT registros_usuario_registrador_id_fkey
    FOREIGN KEY (usuario_registrador_id) REFERENCES usuarios(id) ON DELETE RESTRICT;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'canal_origem_mensagem') THEN
        CREATE TYPE canal_origem_mensagem AS ENUM ('telegram');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'conteudo_mensagem_tipo') THEN
        CREATE TYPE conteudo_mensagem_tipo AS ENUM ('texto', 'foto', 'audio', 'misto');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'processamento_mensagem_status') THEN
        CREATE TYPE processamento_mensagem_status AS ENUM ('pendente', 'processada', 'erro');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lancamento_status') THEN
        CREATE TYPE lancamento_status AS ENUM ('rascunho', 'confirmado', 'consolidado', 'descartado');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'lancamento_tipo_item') THEN
        CREATE TYPE lancamento_tipo_item AS ENUM ('atividade', 'producao', 'ocorrencia', 'pendencia', 'apoio');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'recurso_categoria') THEN
        CREATE TYPE recurso_categoria AS ENUM ('mao_obra', 'equipamento', 'veiculo');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS mensagens_campo (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canal canal_origem_mensagem NOT NULL,
    telegram_chat_id VARCHAR,
    telegram_message_id BIGINT,
    telegram_update_id BIGINT,
    usuario_id INT REFERENCES usuarios(id) ON DELETE SET NULL,
    recebida_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    tipo_conteudo conteudo_mensagem_tipo NOT NULL DEFAULT 'texto',
    texto_bruto TEXT,
    texto_normalizado TEXT,
    payload_json TEXT,
    hash_idempotencia VARCHAR(120) UNIQUE,
    processada_em TIMESTAMPTZ,
    status_processamento processamento_mensagem_status NOT NULL DEFAULT 'pendente',
    erro_processamento TEXT
);

CREATE TABLE IF NOT EXISTS lancamentos_diario (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id INT NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    frente_servico_id INT NOT NULL REFERENCES frentes_servico(id) ON DELETE RESTRICT,
    data_referencia DATE NOT NULL,
    origem_mensagem_id UUID REFERENCES mensagens_campo(id) ON DELETE SET NULL,
    status lancamento_status NOT NULL DEFAULT 'rascunho',
    confianca_extracao SMALLINT,
    resumo_operacional TEXT,
    observacoes_gerais TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmado_em TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS lancamento_itens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lancamento_id UUID NOT NULL REFERENCES lancamentos_diario(id) ON DELETE CASCADE,
    tipo_item lancamento_tipo_item NOT NULL,
    descricao TEXT NOT NULL,
    estaca_inicial DECIMAL(10, 2),
    estaca_final DECIMAL(10, 2),
    unidade VARCHAR(30),
    quantidade DECIMAL(12, 2),
    clima_turno VARCHAR(20),
    severidade VARCHAR(20),
    observacao TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lancamento_recursos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lancamento_id UUID NOT NULL REFERENCES lancamentos_diario(id) ON DELETE CASCADE,
    categoria recurso_categoria NOT NULL,
    nome_recurso VARCHAR(120) NOT NULL,
    quantidade DECIMAL(10, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lancamento_midias (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lancamento_id UUID NOT NULL REFERENCES lancamentos_diario(id) ON DELETE CASCADE,
    mensagem_origem_id UUID REFERENCES mensagens_campo(id) ON DELETE SET NULL,
    external_url VARCHAR,
    storage_path VARCHAR,
    mime_type VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'registros_source_message_id_fkey'
    ) THEN
        ALTER TABLE registros DROP CONSTRAINT registros_source_message_id_fkey;
    END IF;
END $$;

ALTER TABLE registros
ADD CONSTRAINT registros_source_message_id_fkey
FOREIGN KEY (source_message_id) REFERENCES mensagens_campo(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mensagens_campo_telegram_msg ON mensagens_campo(canal, telegram_chat_id, telegram_message_id) WHERE telegram_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_mensagens_campo_status ON mensagens_campo(status_processamento);
CREATE INDEX IF NOT EXISTS idx_mensagens_campo_recebida_em ON mensagens_campo(recebida_em);
CREATE INDEX IF NOT EXISTS idx_lancamentos_diario_data ON lancamentos_diario(data_referencia);
CREATE INDEX IF NOT EXISTS idx_lancamentos_diario_status ON lancamentos_diario(status);
CREATE INDEX IF NOT EXISTS idx_lancamento_itens_lancamento ON lancamento_itens(lancamento_id);
CREATE INDEX IF NOT EXISTS idx_lancamento_recursos_lancamento ON lancamento_recursos(lancamento_id);
CREATE INDEX IF NOT EXISTS idx_lancamento_midias_lancamento ON lancamento_midias(lancamento_id);
