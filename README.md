# Consultor Organizacional Autonomo

Agente de diagnostico organizacional para hackathon. Convierte un event log de
tickets sinteticos en hallazgos trazables, propuestas proporcionadas y un plan
de cambio por horizontes.

> Los datos de demostracion son sinteticos y se usan como diseno experimental.
> No representan personas, equipos ni costos reales.

## Principio

`compute-first, LLM-last`: el codigo calcula metricas, costos, severidad y
simulaciones. Un LLM opcional solo narra evidencia estructurada; no puede
calcular ni proyectar numeros.

## Inicio rapido

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m app.prepare_data
python -m pytest
uvicorn app.api:app --reload
```

Luego consulte `GET /demo/report` o inicie una investigacion con
`POST /investigations`. La respuesta incluye la traza de herramientas y el
reporte ejecutivo.

## API

| Ruta | Proposito |
|---|---|
| `GET /health` | Confirma que el servicio usa datos sinteticos. |
| `GET /demo/report` | Ejecuta el protocolo completo con el dataset demo. |
| `POST /investigations` | Crea una investigacion; acepta `hourly_cost`. |
| `GET /investigations/{id}` | Recupera reporte y traza. |
| `GET /investigations/{id}/trace` | Emite la traza como Server-Sent Events. |
| `POST /datasets/materialize` | Persiste el event log en DuckDB mediante pandas. |

Ejemplo:

```bash
curl -X POST http://localhost:8000/investigations \
  -H "Content-Type: application/json" \
  -d '{"hourly_cost":55}'
```

El adaptador `app.ingestion.normalize_jira_ticket()` normaliza registros tipo
Jira al contrato `Event` y sustituye identificadores de actores por hashes
estables. Adaptadores de Zendesk y ServiceNow deben producir ese mismo
contrato, no introducir modelos paralelos.

## Datos V2

La demo activa usa `data/raw/event_log_v2.jsonl`, con 6.000 tickets y 36.910
eventos operacionales. El CSV es una exportacion equivalente; no es otra fuente
de verdad. La taxonomia y el organigrama declarados se cargan desde `data/raw/`.

Los labels de evaluacion y los ground truth estan bajo `data/private/evaluation/`.
El agente no los carga. `data/legacy/v1/` conserva la demostracion antigua para
regresiones, pero no participa en la API.

## Banco De Pruebas PostgreSQL

La configuracion local esta en `.env`; ese archivo esta ignorado por Git. Copie
`.env.template` para configurar otro ambiente. El `.env` incluido usa credenciales
locales de desarrollo y deja el LLM desactivado porque no hay una clave externa en
este workspace.

```bash
docker compose up -d postgres
. .venv/bin/activate
python scripts/import_v2_to_postgres.py --replace
uvicorn app.api:app --reload
```

El importador carga eventos canonicos, taxonomia y organigrama en Postgres. No lee
ni carga `data/private/evaluation/`. Verifique el estado con:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/config/status
```

Para iniciar la API tambien dentro de Docker, despues de importar los datos:

```bash
docker compose --profile app up -d api
```

## Frontend Y Preguntas

Abra `http://localhost:8000/`. La interfaz permite iniciar un diagnostico, revisar
metricas, handoffs, decisiones, horizontes y la traza de herramientas. El campo de
preguntas usa `POST /investigations/{id}/questions`.

Con `LLM_ENABLED=false`, responde con evidencia determinista. Para Ollama Cloud,
use el endpoint OpenAI-compatible `https://ollama.com/v1`, active
`LLM_ENABLED=true` y configure una clave valida junto a `LLM_MODEL=gpt-oss:20b`.
El modelo recibe solo metricas y hallazgos ya calculados, nunca datos privados,
ground truth ni credenciales. Para validacion local sin Docker, `.env` usa
`DATA_SOURCE=jsonl`; despues de cargar Postgres, cambie esa variable a `postgres`.

## Reglas Operativas

- La API usa Postgres en modo de lectura; el importador es el unico proceso de escritura.
- No publique `.env`, `data/private/` ni la clave del LLM.
- No active un LLM en una URL no confiable.
- El cambio macro sigue requiriendo dos de tres criterios, aunque el LLM este activo.

## Herramientas del agente

- `get_flow_metrics`
- `get_state_queue_times`
- `get_handoff_graph`
- `find_ticket_clusters`
- `classify_business_alignment`
- `classify_change_severity`
- `propose_org_blocks`
- `simulate_change`
- `simulate_horizon_cascade`

## Criterio tactico frente a macro

Cada hallazgo se evalua con tres criterios computables: alcance estructural,
persistencia e impacto en el core. Con cero o uno es tactico; con dos o tres
entra al pipeline macro. Esta regla impide sobreactuar con reestructuraciones
totales ante una friccion aislada.
