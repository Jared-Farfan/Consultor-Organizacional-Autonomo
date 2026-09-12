# Consultor Organizacional Autonomo

Aplicacion de diagnostico organizacional que convierte eventos operativos de tickets en metricas trazables, hallazgos priorizados y propuestas de cambio. Esta construida con el principio **compute-first, LLM-last**: el codigo calcula las cifras y el LLM, si se activa, solo redacta respuestas a partir de evidencia ya calculada.

> Los datos incluidos son sinteticos y experimentales. Los equipos, personas y costos que aparecen en la demo no representan informacion real ni deben usarse para tomar decisiones reales sin validar los datos de origen.

## Que hace

- Mide lead time, tiempo en cola, handoffs, reasignaciones y concentracion de actividad.
- Identifica cuellos de botella, aprobaciones lentas, dependencia de una persona, deuda operativa repetitiva, ping-pong de triaje y desalineacion con el trabajo core.
- Clasifica cada hallazgo como tactico, estructural, organizacional o estrategico.
- Estima el costo anual de cada hallazgo a partir del costo hora configurado.
- Propone bloques organizativos y un cambio gradual por horizontes, con gates verificables.
- Mantiene una traza que explica que herramienta genero cada conclusion.

## Requisitos

- Python 3.11 o superior.
- Docker y Docker Compose solo si se usara PostgreSQL en contenedor.
- Una clave de un proveedor OpenAI-compatible solo si se desea habilitar respuestas LLM.

## Inicio rapido

El modo mas simple lee el JSONL incluido directamente, sin Docker ni base de datos.

```bash
git clone https://github.com/Jared-Farfan/Consultor-Organizacional-Autonomo.git
cd Consultor-Organizacional-Autonomo
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.template .env
```

En `.env`, establezca estas variables para usar el archivo JSONL incluido:

```dotenv
DATA_SOURCE=jsonl
RAW_EVENT_LOG_PATH=data/raw/event_log_v2.jsonl
TAXONOMY_PATH=data/raw/business_taxonomy_v2.json
ORG_CHART_PATH=data/raw/org_chart_declared_v2.json
LLM_ENABLED=false
```

Ejecute el servidor:

```bash
uvicorn app.api:app --reload
```

Abra `http://localhost:8000/`. Confirme la fuente elegida con:

```bash
curl http://localhost:8000/health
```

La respuesta debe indicar `"data_source":"jsonl"` si se siguio el inicio rapido.

## Uso de la interfaz

1. Abra la aplicacion en `http://localhost:8000/`.
2. Escriba un nombre opcional para identificar el escenario, por ejemplo `Costo base`.
3. Defina **Costo hora (USD)**. Es el valor estimado de una hora de trabajo empleada en los problemas detectados; no es un cobro de la aplicacion ni del LLM.
4. Seleccione **Crear diagnostico**.
5. Revise las metricas, los hallazgos, la cascada de horizontes y la traza de investigacion.
6. Cree otra investigacion con otro costo hora para comparar escenarios. El historial permite alternar entre las investigaciones creadas durante la sesion.

El costo anual es una estimacion: cada detector multiplica las horas observadas o inferidas por su regla por el costo hora indicado. Por ejemplo, 1.000 horas de espera con un costo hora de 55 USD equivalen a 55.000 USD anuales estimados. No sustituye una contabilidad financiera validada.

Las investigaciones se almacenan **en memoria**. Se pierden al reiniciar la API; PostgreSQL almacena los eventos de entrada, no el historial de diagnosticos.

## Uso de la API

| Ruta | Uso |
|---|---|
| `GET /` | Interfaz web. |
| `GET /health` | Estado del servicio y fuente de datos activa. |
| `GET /config/status` | Estado seguro de configuracion, sin secretos. |
| `GET /demo/report` | Ejecuta un diagnostico sin guardarlo en el historial. |
| `POST /investigations` | Crea y guarda una investigacion de sesion. |
| `GET /investigations` | Lista las investigaciones de la sesion. |
| `GET /investigations/{id}` | Recupera el reporte y la traza de una investigacion. |
| `POST /investigations/{id}/questions` | Formula una pregunta sobre la evidencia de una investigacion. |
| `GET /investigations/{id}/trace` | Entrega la traza como Server-Sent Events. |
| `POST /datasets/materialize` | Genera los artefactos derivados CSV y DuckDB desde la fuente activa. |

Crear una investigacion por API:

```bash
curl -X POST http://localhost:8000/investigations \
  -H "Content-Type: application/json" \
  -d '{"label":"Escenario costo base","hourly_cost":55}'
```

El campo `hourly_cost` debe ser mayor que cero. Si no se envia, usa `55`. El campo `label` es opcional y admite hasta 80 caracteres.

Preguntar sobre el diagnostico creado:

```bash
curl -X POST http://localhost:8000/investigations/INVESTIGATION_ID/questions \
  -H "Content-Type: application/json" \
  -d '{"question":"Que accion reduce primero el tiempo de onboarding?"}'
```

Reemplace `INVESTIGATION_ID` por el valor `id` de la respuesta al crear la investigacion.

## Fuentes de datos

La aplicacion admite tres valores en `DATA_SOURCE`:

| Fuente | Cuando usarla | Configuracion necesaria |
|---|---|---|
| `jsonl` | Desarrollo local o analisis directo de un log V2. | `RAW_EVENT_LOG_PATH`, `TAXONOMY_PATH`, `ORG_CHART_PATH`. |
| `duckdb` | Consultas locales sobre una version materializada. | `DUCKDB_PATH` y el archivo generado. |
| `postgres` | Entorno compartido o servicio persistente. | `DATABASE_URL` y tablas cargadas. |

Las rutas relativas se resuelven desde la raiz del proyecto. Las variables del entorno de la shell tienen prioridad sobre `.env`, por lo que se puede probar una fuente sin editar el archivo:

```bash
DATA_SOURCE=jsonl LLM_ENABLED=false uvicorn app.api:app --reload
```

### JSONL: fuente directa

`data/raw/event_log_v2.jsonl` es la fuente canonica incluida. Cada linea es un objeto JSON con, como minimo:

```json
{
  "ticket_id": "TCK-00001",
  "ts": "2025-12-16T09:19:23.584192",
  "event_type": "created",
  "actor_hash": "ca6ffc3d276c",
  "from_state": null,
  "to_state": "Backlog",
  "payload": {
    "category": "soporte_reactivo",
    "declared_team": "team_alpha",
    "title": "Descripcion del trabajo"
  }
}
```

El cargador normaliza el log V2 y genera eventos operativos como `assigned`, `handoff`, `approval_requested`, `approval_decided`, `completed_stage` y `resolved`. Para que las metricas sean comparables, un dataset propio debe conservar la semantica de transiciones del formato V2, fechas ISO 8601 y hashes estables en `actor_hash`.

El CSV en `data/raw/event_log_v2.csv` es una exportacion para inspeccion e interoperabilidad; **no** es la fuente que consume la API. Convierta su CSV a JSONL V2 o importe los eventos en PostgreSQL antes de usarlo.

Tambien debe proporcionar estos archivos coherentes con las categorias y equipos del log:

- `business_taxonomy_v2.json`: mapa `{categoria: {label, strategic_value}}`. `strategic_value` usa `alto`, `medio` o `bajo`.
- `org_chart_declared_v2.json`: objeto con `teams` y `members`; cada miembro usa `actor_id_hash`, `declared_team` y `role`.

Ejemplo para cambiar a archivos propios:

```dotenv
DATA_SOURCE=jsonl
RAW_EVENT_LOG_PATH=/ruta/segura/mis_eventos.jsonl
TAXONOMY_PATH=/ruta/segura/mi_taxonomia.json
ORG_CHART_PATH=/ruta/segura/mi_organizacion.json
```

Para integraciones con Jira, el adaptador `app.ingestion.normalize_jira_ticket()` transforma un ticket tipo Jira al contrato interno `Event` y elimina nombres o correos, reemplazandolos por hashes. Los conectores de Zendesk, ServiceNow u otras herramientas deben producir el mismo contrato y no leer material privado de evaluacion.

### DuckDB: fuente local materializada

Genere los artefactos derivados del dataset V2 incluido:

```bash
. .venv/bin/activate
python -m app.prepare_data
```

Esto crea, dentro de `data/derived/`:

- `tickets_observed_v2.csv`, resumen de hechos observables por ticket.
- `organizational_events_v2.duckdb`, tabla `events` normalizada.

Luego seleccione DuckDB:

```dotenv
DATA_SOURCE=duckdb
DUCKDB_PATH=data/derived/organizational_events_v2.duckdb
```

El archivo DuckDB se abre en modo de solo lectura durante el diagnostico. `app.prepare_data` esta preparado para el dataset V2 incluido; para datos propios, carguelos primero con el mismo esquema `events` que se define en `db/init/001_schema.sql`, o use el flujo PostgreSQL.

### PostgreSQL: fuente compartida

1. Copie `.env.template` a `.env` y cambie `POSTGRES_PASSWORD` y `DATABASE_URL` por valores reales.
2. Mantenga `DATA_SOURCE=postgres`.
3. Inicie PostgreSQL y cargue los eventos configurados por las rutas JSONL, taxonomia y organigrama:

```bash
docker compose up -d postgres
. .venv/bin/activate
python scripts/import_v2_to_postgres.py --replace
uvicorn app.api:app --reload
```

`--replace` vacia y vuelve a cargar `events`, `org_members`, `org_teams`, `business_taxonomy` y `dataset_metadata`; uselo solo cuando se desee reemplazar la carga anterior. La API consulta Postgres dentro de una transaccion de solo lectura.

Para ejecutar tambien la API en Docker, despues de importar:

```bash
docker compose --profile app up -d api
```

Revise los servicios con `docker compose ps` y los logs con `docker compose logs -f postgres` o `docker compose logs -f api`.

## LLM opcional

Sin LLM, las preguntas devuelven una respuesta determinista basada en los hallazgos calculados. Para usar Ollama Cloud u otro endpoint OpenAI-compatible, configure:

```dotenv
LLM_ENABLED=true
LLM_BASE_URL=https://ollama.com/v1
LLM_API_KEY=su_clave_secreta
LLM_MODEL=gpt-oss:20b
LLM_TEMPERATURE=0
LLM_STRUCTURED_OUTPUTS=true
```

El modelo recibe solo el resumen ejecutivo, las metricas, los hallazgos y la cascada de horizontes de la investigacion seleccionada. No recibe secretos, los archivos privados de evaluacion ni datos crudos adicionales. El modelo no calcula metricas ni estima importes nuevos.

## Seguridad y datos

- `.env` contiene secretos locales y esta excluido de Git. Nunca lo publique.
- `data/private/` contiene material de evaluacion y ground truth. La API, cargadores y detectores no lo usan como entrada.
- `data/derived/` contiene resultados regenerables y esta excluido de Git.
- La fuente activa de la demo son 6.000 tickets sinteticos y 36.910 eventos en `data/raw/event_log_v2.jsonl`.
- Antes de cargar informacion real, anonimice identificadores personales y revise las politicas de retencion y acceso de su organizacion.

## Pruebas y verificacion

Ejecute la suite completa con el entorno virtual activo:

```bash
.venv/bin/python -m pytest
```

La suite cubre configuracion segura, carga y normalizacion V2, deteccion de hallazgos y comportamiento del agente. Antes de operar, valide tambien la fuente de datos activa:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/config/status
```

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

Un cambio macro requiere al menos dos de tres criterios calculados: alcance estructural, persistencia e impacto en el core. Esta regla evita recomendar una reorganizacion total ante una friccion aislada.
