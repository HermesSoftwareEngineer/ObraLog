-- =====================
-- ENUMS
-- =====================

CREATE TYPE clima AS ENUM ('limpo', 'nublado', 'impraticavel');
CREATE TYPE lado_pista_enum AS ENUM ('direito', 'esquerdo');
CREATE TYPE nivel_acesso AS ENUM ('administrador', 'gerente', 'encarregado');
CREATE TYPE alert_type AS ENUM ('maquina_quebrada', 'acidente', 'falta_material', 'risco_seguranca', 'outro');
CREATE TYPE alert_severity AS ENUM ('baixa', 'media', 'alta', 'critica');
CREATE TYPE alert_status AS ENUM ('aberto', 'em_atendimento', 'aguardando_peca', 'resolvido', 'cancelado');

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
  data DATE NOT NULL,
  frente_servico_id INT NOT NULL REFERENCES frentes_servico(id) ON DELETE CASCADE,
  usuario_registrador_id INT NOT NULL REFERENCES usuarios(id) ON DELETE SET NULL,
  estaca_inicial DECIMAL(10, 2) NOT NULL,
  estaca_final DECIMAL(10, 2) NOT NULL,
  resultado DECIMAL(10, 2) NOT NULL,
  tempo_manha clima NOT NULL,
  tempo_tarde clima NOT NULL,
  pista lado_pista_enum,
  lado_pista lado_pista_enum,
  observacao TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
