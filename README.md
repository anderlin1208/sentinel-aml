# SENTINEL AML — Financial Risk Intelligence

Plataforma de monitoreo transaccional, alertas explicables, investigaciones, topología de cuentas y auditoría. Aplicación para el reto **Prevención de fraudes y lavado de activos**, categoría Riesgos. Diseñada para presentar un flujo real de extremo a extremo sin afirmar capacidades regulatorias no verificadas.

**Stack:** React + Vite + Recharts + Supabase Auth + FastAPI + SQLAlchemy + PostgreSQL (Supabase) + Render.

## Módulos incluidos

1. Centro de control: operaciones, volumen, alertas abiertas, expedientes y distribución de riesgos.
2. Clientes y cuentas: altas individuales con validaciones, códigos únicos y relaciones.
3. Transacciones: registro manual, CSV (500 filas máx.), idempotencia por ID externo, score y evidencias.
4. Alertas: clasificación y visualización de factores, descarte o apertura de expedientes.
5. Investigaciones: apertura, estado, notas, conclusiones y aprobación de cierre confirmado.
6. Red financiera: nodos de cuentas y transferencias recientes, con inspector de conexiones.
7. Motor de reglas: catálogo verídico de los cinco detectores activos.
8. Auditoría: registro de cambios críticos y actos de evaluación.
9. Usuarios y roles: reader/viewer, analyst, supervisor, admin mediante Supabase Auth + API.

## Instalación local SIN entorno virtual (Windows PowerShell)

Requiere: Python 3.11–3.13, Node.js 20+ con npm, Git, cuenta Supabase. Las dependencias de Python se instalan en el usuario (no en venv).

**1. Crear el proyecto Supabase.** Desde el panel de Supabase: proyecto nuevo, Database -> Connect -> copiar la cadena **Session pooler** (puerto 5432, normalmente IPv4) para Postgres. Reemplazar contraseña, protegerla y agregar `?sslmode=require` si no está incluido. En Supabase -> Project Settings -> API Keys obtén la publishable/anon key; en Project URL la dirección HTTPS. En Authentication -> Providers -> Email, activa inicio con correo y contraseña; desactiva altas públicas o administra usuarios mediante invitaciones. Crea un usuario con correo verificado para `ADMIN_EMAIL` desde Authentication -> Users. **No uses la service_role key como anon key y jamás la publiques en el frontend.**

**2. Backend:**

```powershell
cd sentinel-aml\backend
Copy-Item .env.example .env
py -m pip install --user -r requirements.txt
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Edita `backend/.env` ANTES del último comando:

```env
ENV=development
DATABASE_URL=postgresql://postgres.PROJECT_REF:CLAVE_URL_ENCODED@HOST_POOLER_REAL:5432/postgres?sslmode=require
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_ANON_KEY=TU_PUBLISHABLE_KEY
ADMIN_EMAIL=administrador@tudominio.com
CORS_ORIGINS=http://localhost:5173
```

La URL **no debe construirse a mano**: cópiala de Connect y sustituye la contraseña. Caracteres reservados en contraseñas requieren codificación URL. Endpoint de salud: `http://localhost:8000/api/health`, API Swagger: `http://localhost:8000/api/docs`.

**3. Frontend:** abre otra terminal.

```powershell
cd sentinel-aml\frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Editar `frontend/.env`:

```env
VITE_API_URL=http://localhost:8000/api
VITE_SUPABASE_URL=https://PROJECT_REF.supabase.co
VITE_SUPABASE_ANON_KEY=TU_PUBLISHABLE_KEY
```

Abrir `http://localhost:5173`. Inicia sesión con el correo verificado de `ADMIN_EMAIL` (mismo literal, sin diferencias). Para incorporar otro analista: crear la cuenta en Authentication -> Users y hacer que inicie sesión; se registrará como `pending` sin acceso a datos. Cambiar a `analyst` en Equipo y accesos desde la cuenta admin.

**4. Inicializar el flujo:** crear 2 clientes, 2 cuentas PEN, crear operaciones con distintos importes. Las reglas generan alertas al superar umbral; desde Alertas abrir una investigación y registrar notas. No se crean datos artificiales automáticamente en producción.

**5. Pruebas:**

```powershell
cd sentinel-aml\backend
py -m pytest -q
cd ..\frontend
npm run build
```

Para Linux/macOS reemplaza `py` por `python3`, `Copy-Item` por `cp` y usa `python3 -m pip install --user -r requirements.txt`. En algunas instalaciones de Python gestionadas por el sistema (`externally-managed-environment`) el instalador global/user está restringido; no es seguro forzarlo con `--break-system-packages`. Usa Python instalado independientemente o un entorno aislado si el sistema lo requiere.

## Publicación Render con Blueprint

1. Subir la carpeta `sentinel-aml/` a un repositorio Git (SIN archivos `.env`, ni contraseñas).
2. Render -> New -> Blueprint -> seleccionar repositorio -> `render.yaml`.
3. En el servicio `sentinel-aml-api`: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `ADMIN_EMAIL`, `CORS_ORIGINS=https://TU-FRONTEND.onrender.com`. El servicio API tiene health `/api/health`.
4. En el sitio `sentinel-aml-portal`: `VITE_API_URL=https://TU-API.onrender.com/api`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.
5. Construir y desplegar. Si modificas variables `VITE_` en Render, redeploy del frontend porque se embeben en el bundle construido.
6. En Supabase Authentication -> URL Configuration configura Site URL y Redirect URLs con la URL exacta del frontend (para recuperación por correo). Configura el SMTP/plantillas conforme al proyecto.
7. Verifica `GET /api/health`, inicio de sesión, creación de cliente, cuenta, transacción y alerta.

Nota: Render Free puede dormir tras inactividad y causar una primera solicitud lenta; para una demo crítica, usa un servicio con disponibilidad garantizada. Supabase tiene límites de conexión; configura el pooler en modo sesión y guarda el secreto únicamente en el backend. Las dos instancias son servicios independientes.

## Seguridad

- API privada: validación de access token con Supabase Auth en **cada** solicitud y roles server-side.
- CORS permitido únicamente para el frontend configurado.
- Validación Pydantic, FK y unicidad en DB.
- Registros críticos de auditoría; sin acciones bancarias reales.
- Sin generación silenciosa de transacciones ni métricas ficticias.
- Política inicial: usuarios nuevos son `pending` (sin acceso); eleva permisos manualmente.

Consulta `docs/ARQUITECTURA.md` antes de implementar uso sobre datos reales.

## Contrato CSV

```csv
external_id,source_account_id,destination_account_id,amount,occurred_at,channel
```

Los IDs son UUID internos de `accounts` (el módulo cuenta muestra códigos legibles; para importación utiliza los UUID obtenidos en `GET /api/accounts` desde la API autenticada). `occurred_at` debe incluir zona horaria, ej. ISO 8601 con `-05:00`.
