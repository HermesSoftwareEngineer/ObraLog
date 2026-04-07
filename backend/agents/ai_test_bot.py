from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage


# Allow running this file directly: `python backend/agents/ai_test_bot.py`
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from backend.agents.graph import graph
    from backend.agents.llms import llm_main
    from backend.db.models import NivelAcesso
    from backend.db.repository import Repository
    from backend.db.session import SessionLocal
except ImportError:
    from graph import graph
    from llms import llm_main
    from db.models import NivelAcesso
    from db.repository import Repository
    from db.session import SessionLocal


RESET_COMMANDS = {"/reset", "/reset_contexto", "/nova_thread", "/novathread"}


@dataclass
class TestProfile:
    key: str
    display_name: str
    role: str
    persona: str
    tone: str
    behavior: str
    objective: str
    front_rule: str
    scenario_intents: tuple[str, ...]


PROFILES = [
    TestProfile(
        key="piao",
        display_name="Peao de obra",
        role="peao",
        persona="Pouca familiaridade com termos tecnicos, fala de forma direta e descreve o que viu no campo.",
        tone="simples",
        behavior="Traz informacao incompleta, mistura nomes de frente e pode esquecer datas ou quantidades.",
        objective="Testar se o agente consegue transformar relato solto de campo em coleta util de dados de obra.",
        front_rule="Nao cria nem altera frentes de servico; no maximo menciona uma frente de forma vaga ou pede ajuda para identificar qual usar.",
        scenario_intents=(
            "Registrar produtividade com dados incompletos",
            "Misturar pedido valido com ruido e termos vagos",
            "Induzir uso indevido de comando e testar tratamento de erro",
        ),
    ),
    TestProfile(
        key="encarregado",
        display_name="Encarregado de obra",
        role="encarregado",
        persona="Conhece a rotina do canteiro e fala de producao, equipe e andamento do servico.",
        tone="direto",
        behavior="Passa dados objetivos, cobra agilidade e pode trazer correcao de registros anteriores.",
        objective="Testar fluxo de registro, consulta e ajuste de dados com foco em produtividade da frente de obra.",
        front_rule="Nao cria nem altera frentes de servico; deve falar de registros e consultar frentes ja cadastradas, sem tentar cadastra-las.",
        scenario_intents=(
            "Registrar produtividade com dados completos",
            "Registrar produtividade com dados incompletos",
            "Consultar registros por data e por frente",
            "Atualizar registro existente com informacoes contraditorias",
        ),
    ),
    TestProfile(
        key="engenheiro",
        display_name="Engenheiro de obra",
        role="engenheiro",
        persona="Fala com visao de planejamento, consolidacao de campo e controle de frentes de servico.",
        tone="tecnico",
        behavior="Pede organizacao, valida detalhes da obra e pode tentar criar ou ajustar frentes de servico.",
        objective="Testar permissao e encadeamento do agente em cenarios de controle de obra e frentes de servico.",
        front_rule="Pode solicitar criacao, ajuste ou consulta de frentes de servico; use esse perfil para validar se o agente respeita a permissao correta.",
        scenario_intents=(
            "Registrar com ambiguidade de frente de servico",
            "Consultar registros por data e por frente",
            "Registrar produtividade com dados completos",
            "Atualizar registro existente com informacoes contraditorias",
        ),
    ),
]


def _extract_text_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    parts.append(text_value)
        return "\n".join(part for part in parts if part).strip()
    if isinstance(content, dict):
        text_value = content.get("text")
        if isinstance(text_value, str):
            return text_value
    return str(content)


def _ensure_dev_only() -> None:
    env_name = (
        os.environ.get("OBRALOG_ENV")
        or os.environ.get("ENV")
        or os.environ.get("FLASK_ENV")
        or "development"
    ).strip().lower()
    if env_name in {"prod", "production"}:
        raise RuntimeError("O bot de testes automatizado deve rodar apenas em ambiente de desenvolvimento.")


def _ensure_test_fixtures() -> dict:
    seed_frentes = ["Drenagem", "Pavimentacao", "Sinalizacao", "Terraplenagem"]
    run_tag = datetime.now(UTC).strftime("%Y%m%d")

    with SessionLocal() as db:
        users = []
        for level in (NivelAcesso.ADMINISTRADOR, NivelAcesso.GERENTE, NivelAcesso.ENCARREGADO):
            email = f"teste.ia.{level.value}.{run_tag}@obralog.dev"
            user = Repository.usuarios.obter_por_email(db, email)
            if not user:
                user = Repository.usuarios.criar(
                    db=db,
                    nome=f"Teste IA {level.value}",
                    email=email,
                    senha="senha_teste_123",
                    nivel_acesso=level,
                )
            users.append(user)

        existing = {item.nome.lower() for item in Repository.frentes_servico.listar(db)}
        for nome in seed_frentes:
            if nome.lower() not in existing:
                Repository.frentes_servico.criar(db, nome=nome)

    return {
        "admin": users[0],
        "gerente": users[1],
        "encarregado": users[2],
    }


def _build_profile_context(profile: TestProfile) -> str:
    return (
        f"Perfil simulado: {profile.display_name}\n"
        f"Funcao na obra: {profile.role}\n"
        f"Objetivo da simulacao: {profile.objective}\n"
        f"Como fala: {profile.persona}\n"
        f"Tom: {profile.tone}\n"
        f"Comportamento esperado: {profile.behavior}\n"
        f"Regra sobre frentes de servico: {profile.front_rule}\n"
    )


def _build_generator_prompt(profile: TestProfile, scenario: str, history: list[dict], step: int) -> list:
    history_text = "\n".join(f"{item['role']}: {item['text']}" for item in history[-10:]) or "(sem historico)"
    system = SystemMessage(
        content=(
            "Voce eh um gerador de mensagens para testes do ObraLog. O sistema serve para registrar e consultar dados de obra, "
            "como produtividade, registros operacionais e frentes de servico. O agente principal eh o Tiao, assistente do diario de obra. "
            "Seu trabalho e simular usuarios reais de canteiro para validar se o agente entende a intencao, coleta os dados certos, "
            "respeita permissoes e lida bem com ambiguidades e erros. Gere SOMENTE a proxima mensagem do usuario, em pt-BR, curta "
            "(1-3 frases), natural e coerente com o historico. Nao explique estrategia, nao use markdown."
        )
    )
    user = HumanMessage(
        content=(
            f"{_build_profile_context(profile)}"
            f"Cenario: {scenario}\n"
            f"Passo atual: {step}\n"
            "Objetivo do teste: provocar o agente a completar informacoes, confirmar acoes, consultar dados e reagir a pedidos inadequados ou ambguos.\n"
            "Regra estrategica: em alguns momentos, use /reset para reiniciar contexto e aumentar cobertura.\n"
            "Regra importante: somente perfis de engenheiro devem tentar criar ou alterar frentes de servico; peao e encarregado nao devem pedir cadastro de frente, apenas mencionar ou consultar quando fizer sentido.\n"
            "Historico recente:\n"
            f"{history_text}\n\n"
            "Gere a proxima fala do usuario agora, mantendo o papel simulado e o objetivo do cenario."
        )
    )
    return [system, user]


def _build_evaluator_prompt(profile: TestProfile, scenario: str, user_text: str, agent_text: str) -> list:
    rubric = (
        "Avalie a resposta do agente com foco em clareza, coerencia, utilidade, tratamento de erros e aderencia ao objetivo. "
        "Considere tambem se a resposta respeitou o papel simulado e a regra de frentes de servico: peao e encarregado nao devem receber fluxo de cadastro de frente, "
        "enquanto engenheiro pode acionar esse tipo de assunto. "
        "Retorne JSON puro com campos: "
        "overall_score (0-10), clarity (0-10), coherence (0-10), utility (0-10), error_handling (0-10), "
        "purpose_fit (0-10), issues (array de strings), improvements (array de strings), severity (low|medium|high)."
    )
    system = SystemMessage(content="Voce eh avaliador de qualidade de um agente conversacional de obra, com foco em fluxo, permissao e utilidade pratica.")
    user = HumanMessage(
        content=(
            f"{_build_profile_context(profile)}"
            f"Cenario: {scenario}\n"
            f"Mensagem do usuario: {user_text}\n"
            f"Resposta do agente: {agent_text}\n"
            f"{rubric}"
        )
    )
    return [system, user]


def _safe_json_parse(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json", "", 1).strip()
    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {
        "overall_score": 0,
        "clarity": 0,
        "coherence": 0,
        "utility": 0,
        "error_handling": 0,
        "purpose_fit": 0,
        "issues": ["Falha ao parsear avaliacao automatica."],
        "improvements": ["Revisar prompt do avaliador/saida do modelo."],
        "severity": "medium",
    }


def _print_live(role: str, text: str) -> None:
    print(f"[{role}] {text}")


def _append_jsonl(log_path: Path, payload: dict) -> None:
    with log_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _invoke_agent(user_text: str, actor_user_id: int, actor_level: str, thread_id: str) -> str:
    config = {
        "configurable": {
            "thread_id": thread_id,
            "actor_user_id": actor_user_id,
            "actor_level": actor_level,
            "actor_name": "Usuario QA",
            "actor_chat_display_name": "qa-bot",
        }
    }
    response = graph.invoke({"messages": [HumanMessage(content=user_text)]}, config)
    final_message = response["messages"][-1]
    return _extract_text_content(final_message.content)


def _run_single_scenario(
    scenario_id: int,
    max_turns: int,
    actor_user_id: int,
    actor_level: str,
    log_path: Path,
    users_by_level: dict,
    respect_profile_permissions: bool,
) -> dict:
    profile = random.choice(PROFILES)
    scenario = random.choice(profile.scenario_intents)
    thread_id = f"qa:{uuid4().hex}"
    history: list[dict] = []
    issue_count = 0
    high_severity_count = 0

    _print_live("SCENARIO", f"#{scenario_id} | perfil={profile.key} | objetivo={scenario}")
    _append_jsonl(
        log_path,
        {
            "type": "scenario_start",
            "scenario_id": scenario_id,
            "profile": profile.__dict__,
            "scenario": scenario,
            "thread_id": thread_id,
            "execution_actor": {
                "id": actor_user_id,
                "nivel_acesso": actor_level,
            },
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    for step in range(1, max_turns + 1):
        generator_messages = _build_generator_prompt(profile, scenario, history, step)
        generated = llm_main.invoke(generator_messages)
        user_text = _extract_text_content(generated.content).strip()
        if not user_text:
            user_text = "Quero registrar produtividade de hoje, pode me ajudar?"

        if step > 1 and random.random() < 0.12:
            user_text = "/reset"

        _print_live("USER", user_text)

        if user_text.strip().lower() in RESET_COMMANDS:
            thread_id = f"qa:{uuid4().hex}"
            agent_text = "Contexto reiniciado pelo bot de testes com /reset."
            _print_live("AGENT", agent_text)
            history.append({"role": "user", "text": user_text})
            history.append({"role": "assistant", "text": agent_text})
            _append_jsonl(
                log_path,
                {
                    "type": "reset_event",
                    "scenario_id": scenario_id,
                    "step": step,
                    "thread_id": thread_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
            continue

        effective_actor_user_id = actor_user_id
        effective_actor_level = actor_level
        if respect_profile_permissions:
            if profile.key == "engenheiro":
                effective = users_by_level["gerente"]
                effective_actor_user_id = effective.id
                effective_actor_level = effective.nivel_acesso.value if hasattr(effective.nivel_acesso, "value") else str(effective.nivel_acesso)
            elif profile.key in {"encarregado", "piao"}:
                effective = users_by_level["encarregado"]
                effective_actor_user_id = effective.id
                effective_actor_level = effective.nivel_acesso.value if hasattr(effective.nivel_acesso, "value") else str(effective.nivel_acesso)

        try:
            agent_text = _invoke_agent(user_text, effective_actor_user_id, effective_actor_level, thread_id)
        except Exception as exc:
            agent_text = f"ERRO_AGENTE: {exc}"

        _print_live("AGENT", agent_text)

        history.append({"role": "user", "text": user_text})
        history.append({"role": "assistant", "text": agent_text})

        evaluator_messages = _build_evaluator_prompt(profile, scenario, user_text, agent_text)
        evaluation_raw = llm_main.invoke(evaluator_messages)
        evaluation_text = _extract_text_content(evaluation_raw.content)
        evaluation = _safe_json_parse(evaluation_text)

        issues = evaluation.get("issues") or []
        severity = str(evaluation.get("severity", "low")).lower()
        if issues:
            issue_count += len(issues)
        if severity == "high":
            high_severity_count += 1

        _append_jsonl(
            log_path,
            {
                "type": "turn",
                "scenario_id": scenario_id,
                "step": step,
                "profile": profile.key,
                "scenario": scenario,
                "thread_id": thread_id,
                "execution_actor": {
                    "id": effective_actor_user_id,
                    "nivel_acesso": effective_actor_level,
                },
                "user": user_text,
                "agent": agent_text,
                "evaluation": evaluation,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        time.sleep(0.15)

    summary = {
        "scenario_id": scenario_id,
        "profile": profile.key,
        "scenario": scenario,
        "turns": max_turns,
        "issues_found": issue_count,
        "high_severity_events": high_severity_count,
    }
    _append_jsonl(
        log_path,
        {
            "type": "scenario_end",
            "summary": summary,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
    return summary


def run(args: argparse.Namespace) -> Path:
    _ensure_dev_only()
    users = _ensure_test_fixtures()
    actor = users[args.actor_level]

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_path = Path(args.log_file) if args.log_file else log_dir / f"ai_test_run_{run_id}.jsonl"

    _append_jsonl(
        log_path,
        {
            "type": "run_start",
            "run_id": run_id,
            "args": vars(args),
            "actor": {
                "id": actor.id,
                "email": actor.email,
                "nivel_acesso": actor.nivel_acesso.value if hasattr(actor.nivel_acesso, "value") else str(actor.nivel_acesso),
            },
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

    _print_live("RUN", f"Log de testes: {log_path}")

    scenario_id = 1
    summaries = []
    while True:
        summary = _run_single_scenario(
            scenario_id=scenario_id,
            max_turns=args.max_turns,
            actor_user_id=actor.id,
            actor_level=actor.nivel_acesso.value if hasattr(actor.nivel_acesso, "value") else str(actor.nivel_acesso),
            log_path=log_path,
            users_by_level=users,
            respect_profile_permissions=args.respect_profile_permissions,
        )
        summaries.append(summary)
        scenario_id += 1

        if not args.continuous and scenario_id > args.scenarios:
            break

    _append_jsonl(
        log_path,
        {
            "type": "run_end",
            "scenarios_executed": len(summaries),
            "total_issues": sum(item["issues_found"] for item in summaries),
            "total_high_severity_events": sum(item["high_severity_events"] for item in summaries),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
    _print_live("RUN", "Execucao finalizada.")
    return log_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bot de testes automatizado com IA para validar conversas do agente ObraLog.",
    )
    parser.add_argument("--scenarios", type=int, default=5, help="Quantidade de cenarios por execucao.")
    parser.add_argument("--max-turns", type=int, default=8, help="Quantidade maxima de turnos por cenario.")
    parser.add_argument(
        "--actor-level",
        choices=["admin", "gerente", "encarregado"],
        default="encarregado",
        help="Perfil de permissao usado para executar as tools no grafo.",
    )
    parser.add_argument(
        "--log-dir",
        default="backend/agents/test_logs",
        help="Diretorio para armazenar logs estruturados dos testes.",
    )
    parser.add_argument("--log-file", default="", help="Arquivo JSONL especifico para salvar os logs.")
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Executa continuamente, gerando novos cenarios ate interrupcao manual.",
    )
    parser.add_argument(
        "--respect-profile-permissions",
        action="store_true",
        default=True,
        help="Alinha o nível de acesso efetivo ao perfil simulado (ex.: engenheiro usa permissões de gerente).",
    )
    parser.add_argument(
        "--no-respect-profile-permissions",
        action="store_false",
        dest="respect_profile_permissions",
        help="Mantém sempre o mesmo actor-level para todos os cenários.",
    )
    return parser


if __name__ == "__main__":
    parsed_args = _build_parser().parse_args()
    try:
        output_path = run(parsed_args)
        print(f"Log salvo em: {output_path}")
    except KeyboardInterrupt:
        print("Execucao interrompida pelo usuario.")
        sys.exit(130)
    except Exception as exc:
        print(f"Falha ao executar bot de testes: {exc}")
        sys.exit(1)