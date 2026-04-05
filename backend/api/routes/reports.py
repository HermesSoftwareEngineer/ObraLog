from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from flask import Blueprint, jsonify

from backend.db.repository import Repository
from backend.db.session import SessionLocal

router = Blueprint("reports", __name__)


def _to_float(value):
	if value is None:
		return 0.0
	if isinstance(value, Decimal):
		return float(value)
	return float(value)


@router.get("/api/v1/dashboard/overview")
def dashboard_overview():
	with SessionLocal() as db:
		usuarios = Repository.usuarios.listar(db)
		frentes = Repository.frentes_servico.listar(db)
		registros = Repository.registros.listar(db)

	today = date.today()
	last_7_days = [today - timedelta(days=i) for i in range(6, -1, -1)]

	registros_por_dia = defaultdict(int)
	progresso_por_dia = defaultdict(float)
	progresso_por_frente = defaultdict(float)

	for registro in registros:
		if registro.data:
			registros_por_dia[registro.data.isoformat()] += 1

		if registro.resultado is not None:
			result_value = _to_float(registro.resultado)
			if registro.data:
				progresso_por_dia[registro.data.isoformat()] += result_value
			frente_key = str(registro.frente_servico_id) if registro.frente_servico_id is not None else "sem_frente"
			progresso_por_frente[frente_key] += result_value

	series_registros_7d = [
		{
			"date": day.isoformat(),
			"total": registros_por_dia.get(day.isoformat(), 0),
		}
		for day in last_7_days
	]

	series_progresso_7d = [
		{
			"date": day.isoformat(),
			"resultado_total": round(progresso_por_dia.get(day.isoformat(), 0.0), 2),
		}
		for day in last_7_days
	]

	chart_progresso_frente = [
		{
			"frente_servico_id": None if key == "sem_frente" else int(key),
			"resultado_total": round(value, 2),
		}
		for key, value in progresso_por_frente.items()
	]
	chart_progresso_frente.sort(key=lambda item: item["resultado_total"], reverse=True)

	payload = {
		"kpis": {
			"usuarios_total": len(usuarios),
			"frentes_servico_total": len(frentes),
			"registros_total": len(registros),
			"progresso_total": round(sum(_to_float(reg.resultado) for reg in registros if reg.resultado is not None), 2),
		},
		"charts": {
			"registros_por_dia_7d": series_registros_7d,
			"progresso_por_dia_7d": series_progresso_7d,
			"progresso_por_frente": chart_progresso_frente,
		},
	}
	return jsonify(payload)
