CREATE TABLE IF NOT EXISTS telegram_link_codes (
  id SERIAL PRIMARY KEY,
  user_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  code VARCHAR(32) NOT NULL UNIQUE,
  generated_by_user_id INT REFERENCES usuarios(id) ON DELETE SET NULL,
  expires_at TIMESTAMP NOT NULL,
  used_at TIMESTAMP NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_telegram_link_codes_user ON telegram_link_codes(user_id);
CREATE INDEX IF NOT EXISTS idx_telegram_link_codes_expires_at ON telegram_link_codes(expires_at);
CREATE INDEX IF NOT EXISTS idx_telegram_link_codes_used_at ON telegram_link_codes(used_at);
