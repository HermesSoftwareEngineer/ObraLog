-- =====================
-- ENUMS
-- =====================

CREATE TYPE clima AS ENUM ('limpo', 'nublado', 'impraticavel');
CREATE TYPE lado_pista_enum AS ENUM ('direito', 'esquerdo');
CREATE TYPE nivel_acesso AS ENUM ('administrador', 'gerente', 'encarregado');
CREATE TYPE alert_type AS ENUM ('maquina_quebrada', 'acidente', 'falta_material', 'risco_seguranca', 'outro');
CREATE TYPE alert_severity AS ENUM ('baixa', 'media', 'alta', 'critica');
CREATE TYPE alert_status AS ENUM ('aberto', 'em_atendimento', 'aguardando_peca', 'resolvido', 'cancelado');
CREATE TYPE canal_origem_mensagem AS ENUM ('telegram');
CREATE TYPE conteudo_mensagem_tipo AS ENUM ('texto', 'foto', 'audio', 'misto');
CREATE TYPE processamento_mensagem_status AS ENUM ('pendente', 'processada', 'erro');
CREATE TYPE registro_status AS ENUM ('pendente', 'consolidado', 'revisado', 'ativo', 'descartado');

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =====================
-- TABELA: Usuários
-- =====================

CREATE TABLE usuarios (
  id SERIAL PRIMARY KEY,
  nome VARCHAR NOT NULL,
  email VARCHAR NOT NULL UNIQUE,
  senha VARCHAR NOT NULL,
  telefone VARCHAR,
  telegram_chat_id VARCHAR UNIQUE,
  telegram_thread_id VARCHAR UNIQUE,
  nivel_acesso nivel_acesso DEFAULT 'encarregado',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================
-- TABELA: Frentes de Serviço
-- =====================

CREATE TABLE frentes_servico (
  id SERIAL PRIMARY KEY,
  nome VARCHAR NOT NULL,
  encarregado_responsavel INT REFERENCES usuarios(id) ON DELETE SET NULL,
  observacao TEXT
);

-- =====================
-- TABELA: Registros (Diário de Obra)
-- =====================

CREATE TABLE registros (
  id SERIAL PRIMARY KEY,
  status registro_status NOT NULL DEFAULT 'pendente',
  data DATE,
  frente_servico_id INT REFERENCES frentes_servico(id) ON DELETE CASCADE,
  usuario_registrador_id INT REFERENCES usuarios(id) ON DELETE RESTRICT,
  estaca_inicial DECIMAL(10, 2),
  estaca_final DECIMAL(10, 2),
  resultado DECIMAL(10, 2),
  tempo_manha clima,
  tempo_tarde clima,
  lado_pista lado_pista_enum,
  observacao TEXT,
  raw_text TEXT,
  source_message_id UUID,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE registros
  ADD CONSTRAINT ck_registros_consolidado_campos_basicos
  CHECK (
    status <> 'consolidado'
    OR (
      data IS NOT NULL
      AND frente_servico_id IS NOT NULL
      AND usuario_registrador_id IS NOT NULL
      AND estaca_inicial IS NOT NULL
      AND estaca_final IS NOT NULL
      AND resultado IS NOT NULL
      AND tempo_manha IS NOT NULL
      AND tempo_tarde IS NOT NULL
    )
  );

CREATE TABLE registro_imagens (
  id SERIAL PRIMARY KEY,
  registro_id INT NOT NULL REFERENCES registros(id) ON DELETE CASCADE,
  storage_path VARCHAR,
  external_url VARCHAR,
  mime_type VARCHAR,
  file_size INT,
  origem VARCHAR NOT NULL DEFAULT 'api',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================
-- TABELA: Códigos de vínculo Telegram
-- =====================

CREATE TABLE telegram_link_codes (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  code VARCHAR(32) NOT NULL UNIQUE,
  generated_by_user_id INT REFERENCES usuarios(id) ON DELETE SET NULL,
  expires_at TIMESTAMP NOT NULL,
  used_at TIMESTAMP NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE mensagens_campo (
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

ALTER TABLE registros
  ADD CONSTRAINT registros_source_message_id_fkey
  FOREIGN KEY (source_message_id) REFERENCES mensagens_campo(id) ON DELETE SET NULL;

CREATE TABLE registro_auditoria (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  registro_id INT NOT NULL REFERENCES registros(id) ON DELETE CASCADE,
  acao VARCHAR(30) NOT NULL,
  diff_json TEXT NOT NULL,
  actor_user_id INT REFERENCES usuarios(id) ON DELETE SET NULL,
  actor_level VARCHAR(30),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code VARCHAR(20) UNIQUE NOT NULL,
  type alert_type NOT NULL,
  severity alert_severity NOT NULL,
  reported_by INT NOT NULL REFERENCES usuarios(id),
  telegram_message_id BIGINT,
  title VARCHAR(200) NOT NULL,
  description TEXT NOT NULL,
  raw_text TEXT,
  location_detail VARCHAR(200),
  equipment_name VARCHAR(100),
  photo_urls TEXT[],
  status alert_status NOT NULL DEFAULT 'aberto',
  priority_score SMALLINT,
  notified_at TIMESTAMPTZ,
  notified_channels TEXT[],
  resolved_by INT REFERENCES usuarios(id),
  resolved_at TIMESTAMPTZ,
  resolution_notes TEXT,
  is_read BOOLEAN NOT NULL DEFAULT false,
  read_at TIMESTAMPTZ,
  read_by INT REFERENCES usuarios(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE alert_reads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  alert_id UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
  worker_id INT NOT NULL REFERENCES usuarios(id),
  read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (alert_id, worker_id)
);

-- =====================
-- INDEXES (performance)
-- =====================

CREATE INDEX idx_registros_data ON registros(data);
CREATE INDEX idx_registros_status ON registros(status);
CREATE INDEX idx_registros_frente_servico ON registros(frente_servico_id);
CREATE INDEX idx_registros_usuario ON registros(usuario_registrador_id);
CREATE INDEX idx_registro_imagens_registro ON registro_imagens(registro_id);
CREATE INDEX idx_frentes_servico_encarregado ON frentes_servico(encarregado_responsavel);
CREATE INDEX idx_usuarios_telegram_chat_id ON usuarios(telegram_chat_id);
CREATE UNIQUE INDEX idx_usuarios_telegram_thread_id_unique ON usuarios(telegram_thread_id) WHERE telegram_thread_id IS NOT NULL;
CREATE UNIQUE INDEX idx_usuarios_telefone_unique ON usuarios(telefone) WHERE telefone IS NOT NULL;
CREATE INDEX idx_telegram_link_codes_user ON telegram_link_codes(user_id);
CREATE INDEX idx_telegram_link_codes_expires_at ON telegram_link_codes(expires_at);
CREATE INDEX idx_telegram_link_codes_used_at ON telegram_link_codes(used_at);
CREATE INDEX idx_alerts_code ON alerts(code);
CREATE INDEX idx_alerts_reported_by ON alerts(reported_by);
CREATE INDEX idx_alert_reads_alert_id ON alert_reads(alert_id);
CREATE INDEX idx_alert_reads_worker_id ON alert_reads(worker_id);
CREATE UNIQUE INDEX uq_mensagens_campo_telegram_msg ON mensagens_campo(canal, telegram_chat_id, telegram_message_id) WHERE telegram_message_id IS NOT NULL;
CREATE INDEX idx_mensagens_campo_status ON mensagens_campo(status_processamento);
CREATE INDEX idx_mensagens_campo_recebida_em ON mensagens_campo(recebida_em);
CREATE INDEX idx_registro_auditoria_registro ON registro_auditoria(registro_id);
