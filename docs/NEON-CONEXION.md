# Configuración Neon verificada

Proyecto: super-base-33383770. Organización: Pablo (org-silent-salad-03912100). Rama: production (br-crimson-smoke-b8ni1ori).

Consola: https://console.neon.tech/app/projects/super-base-33383770/

La vinculación está en la copia barriocuenta-cloud del área de trabajo. La instalación local en Documents/Codex/2026-10-26/qui/outputs/barriocuenta conserva su base y su conexión. No se sustituyó su .env.

## Cambios realizados

- Instalación global del CLI oficial Neon 8.13.2.
- neon init con la organización, proyecto y rama solicitados; neon.ts declara solo Postgres y conserva el acceso propio de Flask.
- La primera vinculación se escribió offline porque faltaba autenticación. neon login completó el acceso y los comandos posteriores verificaron el proyecto.
- neon init instaló los plugins y habilidades para los editores que detectó en el equipo, además de la configuración MCP de GitHub Copilot CLI. No se ejecutaron instalaciones adicionales de MCP después del init.
- neon deploy confirmó que production coincidía con la política y guardó DATABASE_URL, DATABASE_URL_UNPOOLED y NEON_BRANCH en .env.local.
- Carga de .env.local antes de .env, con prioridad de las variables del proceso. Psycopg/SQLAlchemy se conservan: conexión agrupada para operaciones y directa para cambios del esquema.
- Se añadieron pruebas de prioridad de configuración y conexión directa. La copia de nube quedó en APP_MODE=production para impedir la carga accidental de muestras mediante backend.seed.

## Salidas verificadas

```text
neon --version
8.13.2

neon config plan
No changes — branch production already matches the policy.
Utilized services: Postgres

neon deploy
No changes — branch production already matches the policy.
Pulled 3 Neon variables into .env.local
Postgres DATABASE_URL, DATABASE_URL_UNPOOLED
Branch NEON_BRANCH

npm run build
vite v6.4.5 building for production...
1574 modules transformed.
built in 3.19s

python -B -m unittest discover -s tests -v
Ran 58 tests in 44.585s
OK

python -B tests/check_neon_live.py --env .env.neon-test --test-branch codex-verificacion-neon
Servidor HTTP iniciado en 127.0.0.1:5601: OK
Neon real: conexión agrupada TLS y esquema por conexión directa: OK
HTTP: health, login/2FA, cuentas, estados recuperados, simulación, venta idempotente, stock y cobranza persistida: OK
```

Se creó una rama temporal desde production, se probaron allí el esquema y las operaciones con datos ficticios y se retiró al terminar. El servidor HTTP de pruebas también se cerró. Después se aplicó y verificó en production el esquema de 16 tablas de aplicación, además de la tabla de versiones. Production quedó con cero usuarios y sin datos de muestra.

## Límites y siguientes pasos

- No se publicó la web en Render y no se construyó Docker en este equipo, que no tiene Docker instalado.
- No se configuró una clave real de Brevo ni se envió correo real. El segundo factor del recorrido HTTP utilizó el buzón de desarrollo en la rama temporal.
- El acceso público requiere configurar Brevo y el primer administrador en Render, tal como indica el manual. No se creó una contraseña por defecto en production.
- La advertencia de Node DEP0190 apareció durante neon init; el comando terminó y las dependencias y compilación posteriores pasaron.
- El init offline no acreditaba una conexión real por sí solo; ese estado quedó resuelto mediante login, deploy y las pruebas contra Neon.

Las cadenas privadas están excluidas del repositorio y del ZIP de despliegue. No compartir .env.local ni capturas de sus valores.
