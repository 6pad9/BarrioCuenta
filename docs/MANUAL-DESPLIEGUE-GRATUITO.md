# Manual para publicar BarrioCuenta gratis

Guía para Pablo Chumacero. Preparada el 29 de octubre de 2026.

El resultado será una dirección HTTPS pública que podrás compartir con tu grupo y abrir aunque tu computadora esté apagada. Usaremos Render para la aplicación, Neon para PostgreSQL y Brevo para los códigos e invitaciones por correo. El código ya está adaptado; falta configurar tus cuentas y publicar.

## Estado de Neon ya configurado

El proyecto existente [super-base-33383770](https://console.neon.tech/app/projects/super-base-33383770/) de la organización Pablo está vinculado a la copia de nube, rama production. La herramienta oficial guardó DATABASE_URL y DATABASE_URL_UNPOOLED en el archivo privado .env.local. Usa esos dos valores en Render; no subas ese archivo a GitHub. La configuración de la copia de nube está en modo producción y no incluye credenciales de Brevo ni una contraseña inicial elegida por ti.

El esquema se probó primero en una rama temporal con datos ficticios y luego se aplicó a production sin cargar datos de muestra. La publicación de la web y el correo real siguen pendientes de tus cuentas de Render y Brevo. Si utilizas este proyecto ya configurado, no crees otro en el apartado 2.

## 1 Qué necesitas antes de empezar

- Una cuenta en [GitHub](https://github.com), otra en [Neon](https://neon.com), otra en [Brevo](https://www.brevo.com) y otra en [Render](https://render.com).
- Acceso al correo que usarás para entrar como administrador. Puedes utilizar chumaceropablo16@gmail.com.
- El ZIP de despliegue entregado junto a este manual.
- Una contraseña nueva de al menos 12 caracteres, con mayúscula, minúscula y número. Guárdala en tu administrador de contraseñas.

Selecciona los planes **Free**. No necesitas comprar un dominio: Render proporciona una dirección terminada en `onrender.com` y HTTPS. Si algún proveedor solicita verificaciones de cuenta, complétalas antes de continuar; la elegibilidad y las condiciones gratuitas dependen del proveedor.

La publicación inicial utiliza una base nueva. No traslada automáticamente los registros de tu computadora. La aplicación local y sus datos permanecen separados. Este procedimiento está pensado para la presentación académica con datos ficticios.

## 2 Crear la base en Neon

1. Entra en [la consola de Neon](https://console.neon.tech) y crea un proyecto.
2. Ponle un nombre reconocible, por ejemplo `barriocuenta`.
3. Selecciona el plan **Free**. Si está disponible, elige una región cercana a Virginia, donde situaremos Render.
4. Abre **Connect**. Selecciona tu base, por ejemplo `neondb`, y una conexión PostgreSQL.
5. Activa **Connection pooling** si aparece. El servidor suele contener `-pooler`.
6. Copia **solo la cadena de conexión**, sin el comando `psql` ni sus comillas externas. Su forma es:

```text
postgresql://USUARIO:CONTRASEÑA@SERVIDOR.neon.tech/neondb?sslmode=require&channel_binding=require
```

7. Guárdala temporalmente de forma privada. Se pegará como `DATABASE_URL` en Render.
8. Desactiva Connection pooling, copia también la conexión directa y guárdala como `DATABASE_URL_UNPOOLED`. La aplicación usa la agrupada para las operaciones y la directa para actualizar el esquema.

Conserva los parámetros de seguridad que Neon incluya, como `sslmode=require` y `channel_binding=require`. BarrioCuenta adapta automáticamente el controlador a psycopg. No sustituyas la dirección por `localhost` y no subas esa cadena a GitHub.

**Resultado esperado:** tienes una base PostgreSQL vacía y su conexión privada.

## 3 Preparar el correo en Brevo

1. Entra en Brevo con su plan gratuito y completa las verificaciones de cuenta que solicite.
2. Busca **Settings / Configuración → Senders, domains & dedicated IPs / Remitentes y dominios**. Los nombres pueden variar según el idioma.
3. Añade un remitente: nombre `BarrioCuenta` y una dirección de correo que controles.
4. Abre el mensaje de verificación que llegue a esa dirección y confirma el remitente.
5. Si Brevo solicita autenticar un dominio propio o aprobar el envío transaccional, termina ese proceso antes del despliegue. No inventes un remitente `@barriocuenta.local` o un dominio que no controles. El uso de direcciones de proveedores gratuitos está sujeto a las condiciones de Brevo y puede afectar la entrega.
6. Busca **SMTP & API → API Keys / Claves API** y crea una clave para este proyecto.
7. Guarda la **clave API**, no la contraseña de SMTP. Se pegará como `BREVO_API_KEY` en Render.
8. Anota también el correo del remitente verificado: será `MAIL_FROM_EMAIL`.

Render gratuito bloquea los puertos SMTP habituales. Por eso BarrioCuenta usa la API HTTPS de Brevo. En internet ya no habrá un buzón Mailpit para leer códigos: el usuario los recibirá en su correo real.

**Resultado esperado:** tienes un remitente habilitado y una clave API. No es necesario enviar un correo de prueba desde el código antes de configurar Render.

## 4 Subir el código a GitHub

1. Extrae el ZIP de despliegue en una carpeta nueva de tu computadora.
2. En GitHub, pulsa **New repository / Nuevo repositorio**.
3. Nombre sugerido: `barriocuenta`. Selecciona **Private / Privado** y crea el repositorio.
4. Pulsa **uploading an existing file** o **Add file → Upload files**.
5. Abre la carpeta extraída y arrastra **su contenido**, incluyendo las carpetas `backend`, `src`, `tests` y `docs`.
6. Comprueba que `Dockerfile`, `render.yaml`, `.dockerignore`, `.gitignore`, `requirements.txt` y `package.json` queden en la raíz del repositorio. No subas únicamente el archivo ZIP. Tampoco coloques todo dentro de una carpeta adicional.
7. Escribe un mensaje, por ejemplo `Preparar despliegue de BarrioCuenta`, y pulsa **Commit changes**.

El paquete de despliegue no incluye la base local, contraseñas reales, mensajes, certificados ni respaldos. No añadas `.env`, `runtime`, `vendor`, `tools`, `node_modules`, archivos `.db` o `.dump`. La plantilla `.env.render.example` está vacía y sirve como referencia; no debes rellenarla con secretos y subirla.

Si Windows oculta las extensiones, verifica que el archivo se llame exactamente `Dockerfile`, sin `.txt` al final.

**Resultado esperado:** al abrir el repositorio ves `Dockerfile` y `backend` directamente en su página principal.

## 5 Crear el servicio en Render

1. Entra en [el panel de Render](https://dashboard.render.com).
2. Pulsa **New → Web Service**.
3. Conecta GitHub y concede acceso al repositorio privado `barriocuenta`.
4. Selecciona ese repositorio y la rama que acabas de subir, normalmente `main`.
5. Configura los campos:

| Campo | Valor |
|---|---|
| Name | `barriocuenta` o un nombre disponible |
| Language / Runtime | **Docker** |
| Region | **Virginia**, si está disponible |
| Root Directory | Vacío, si subiste el contenido a la raíz |
| Dockerfile Path | `./Dockerfile` |
| Docker Command | Vacío; el archivo ya contiene el arranque |
| Instance Type | **Free** |
| Health Check Path | `/api/health` |

No necesitas instalar Docker en tu computadora: Render construye la imagen. No agregues un comando de construcción de Python o Node: el `Dockerfile` instala Python, compila React e inicia Gunicorn.

**No crees una base Render Postgres gratuita para esta guía:** usaremos Neon. La base gratuita de Render caduca a los 30 días según sus condiciones actuales.

## 6 Completar las variables privadas

Antes de pulsar Deploy, abre **Environment / Variables de entorno**. Añade cada fila por separado; no incluyas comillas externas en los valores del panel.

| Variable | Valor que debes escribir |
|---|---|
| `APP_MODE` | `production` |
| `MAIL_PROVIDER` | `brevo` |
| `AUTO_PROCESS_CUTS` | `1` |
| `AUTO_CUTS_INTERVAL_SECONDS` | `60` |
| `DATABASE_URL` | Cadena completa copiada de Neon |
| `DATABASE_URL_UNPOOLED` | Conexión directa de Neon, sin `-pooler` en el servidor |
| `BREVO_API_KEY` | Clave API creada en Brevo |
| `MAIL_FROM_EMAIL` | Dirección del remitente verificado en Brevo |
| `MAIL_FROM_NAME` | `BarrioCuenta` |
| `BOOTSTRAP_ADMIN_EMAIL` | Tu correo real de acceso; por ejemplo chumaceropablo16@gmail.com |
| `BOOTSTRAP_ADMIN_PASSWORD` | Tu contraseña nueva de 12 caracteres o más |
| `BOOTSTRAP_ADMIN_NAME` | `Pablo Chumacero` — opcional |

`PUBLIC_URL` es opcional. La aplicación toma automáticamente la dirección que Render proporciona. Si después utilizas un dominio propio, agrega `PUBLIC_URL=https://TU-DOMINIO` sin rutas ni fragmentos.

No agregues `DATABASE_HOST=127.0.0.1`, `SMTP_HOST`, `SMTP_PORT` ni `COOKIE_SECURE=0` para esta publicación. No copies todo el `.env` de tu instalación local.

Las variables `PRIVACY_RESPONSIBLE`, `PRIVACY_ADDRESS`, `PRIVACY_CONTACT`, `PRIVACY_OPERATOR` y `PRIVACY_OPERATOR_CONTACT` permiten personalizar la política. Si no las agregas, se conservan los datos académicos de Pablo y la referencia a UPC San Miguel, sin atribuir a la universidad responsabilidad por el proyecto.

## 7 Publicar y comprobar el primer arranque

1. Revisa que el plan elegido sea **Free** y pulsa **Deploy Web Service**.
2. Espera a que Render termine de descargar dependencias y compilar. En **Logs** verás la construcción de la imagen y el arranque de Gunicorn.
3. Durante ese primer arranque se crean las tablas y un único administrador de plataforma, siempre que la base esté vacía.
4. Cuando el estado sea **Live**, abre la dirección HTTPS que Render muestre. Se parecerá a `https://barriocuenta-xxxx.onrender.com`, pero debes usar tu URL real.
5. Para verificar el servicio, abre esa misma dirección terminada en `/api/health`. Debe responder:

```json
{"application":"BarrioCuenta","status":"ok"}
```

6. Entra con `BOOTSTRAP_ADMIN_EMAIL` y la contraseña que elegiste.
7. Abre la bandeja de ese correo real, busca **Tu código BarrioCuenta** y escribe el código de seis dígitos. Revisa también spam. El código caduca a los cinco minutos con la configuración predeterminada.

No utilices `admin@demo.local` ni `Barrio2026!` en la publicación nueva. Las credenciales locales no se trasladan ni se crean automáticamente en la nube. Tampoco se activa el reloj simulado.

**Resultado esperado:** ves el módulo de tiendas del administrador de plataforma.

## 8 Crear el negocio y probar los tres perfiles

1. Como plataforma, registra una tienda ficticia.
2. En **Usuarios y accesos**, crea su administrador de negocio con un correo real al que tengas acceso y una contraseña nueva. El remitente de Brevo y el destinatario de acceso pueden ser distintos.
3. Cierra sesión e ingresa como ese administrador. El segundo factor llega al correo que le asignaste.
4. Registra un producto de prueba, su stock y su precio al crédito.
5. Registra un cliente ficticio, informa la política y configura su cuenta, tasa, límite y calendario.
6. Simula una venta y confirma solo si los importes coinciden con lo esperado.
7. Desde la cuenta, invita al cliente al portal usando otro correo real disponible. Cada usuario debe tener un correo único.
8. El cliente abre el enlace recibido, establece su contraseña y acepta la política. Después inicia sesión y completa su propio segundo factor.
9. Comprueba que ve únicamente sus cuentas y cronogramas.
10. Actualiza la página o vuelve a desplegar: las operaciones deben seguir en Neon.

Puedes usar correos con alias si tu proveedor los admite, pero comprueba primero su recepción. No introduzcas datos personales o deudas reales para la exposición.

## 9 Retirar la contraseña de inicialización

Cuando hayas comprobado el acceso del primer administrador:

1. En Render, abre **Environment**.
2. Elimina `BOOTSTRAP_ADMIN_PASSWORD` y, si quieres, `BOOTSTRAP_ADMIN_EMAIL` y `BOOTSTRAP_ADMIN_NAME`.
3. Guarda y deja que Render vuelva a desplegar.
4. Confirma que puedes entrar con la misma cuenta y contraseña.

La contraseña se conserva como hash en Neon. Los siguientes arranques no crean otro administrador ni cambian la contraseña existente. Guarda tus credenciales: esta versión todavía no dispone de recuperación de contraseña por autoservicio. No cambies la conexión a otra base vacía sin configurar nuevamente la inicialización.

## 10 Cómo se generan los estados en el plan gratuito

Render puede suspender el servicio cuando no hay visitas. No se mantiene un segundo proceso permanente ni un servicio cron de pago. Al consultar cuentas o estados desde una sesión de negocio o cliente, BarrioCuenta recupera los cortes pendientes, con sus fechas históricas, como máximo una vez cada 60 segundos por proceso.

Por eso un estado no se emite exactamente en el instante del corte mientras la aplicación duerme: aparecerá en la primera consulta autenticada posterior. El total de cobranza se calcula a la fecha actual. El endpoint público de salud no genera estados ni mantiene artificialmente despierta la aplicación.

## 11 Actualizar el proyecto después

1. Conserva un respaldo de Neon antes de un cambio importante del esquema.
2. Modifica los archivos de código y súbelos al mismo repositorio mediante un nuevo commit.
3. Si el despliegue automático está habilitado, Render construirá la nueva versión. En caso contrario, usa **Manual Deploy → Deploy latest commit**.
4. Revisa **Logs** y `/api/health`.
5. Prueba el acceso, una cuenta y un estado. Las claves permanecen en Environment y los datos en Neon.

No ejecutes `backend.seed` para reinicializar una publicación. El esquema se actualiza al arrancar; no se borran ni reemplazan automáticamente sus usuarios y operaciones.

## 12 Resolver problemas frecuentes

| Problema | Qué revisar |
|---|---|
| Render no encuentra Dockerfile | Debe estar en la raíz; revisa Root Directory y que no se llame Dockerfile.txt. |
| Falla `npm ci` | Sube package.json y package-lock.json juntos. Revisa el error completo del build. |
| Configura DATABASE_URL o no se permite base local | Pega la cadena real de Neon, no la de PostgreSQL de tu PC ni un comando psql completo. |
| Error de contraseña o conexión a PostgreSQL | Copia otra vez la cadena desde Neon; conserva su codificación y parámetros TLS. |
| Falta PUBLIC_URL | En Render suele detectarse sola; si hace falta, pega tu URL pública HTTPS exacta en esa variable. |
| Falta administrador inicial | En una base vacía, agrega correo real y contraseña válida en BOOTSTRAP_ADMIN_EMAIL/PASSWORD. |
| El servicio inicia pero no llega el código | Revisa API Key, remitente verificado, aprobación transaccional, cuota y registros de correo de Brevo; luego spam y Reenviar código. |
| No fue posible enviar el correo | Usa una clave API de Brevo, no una clave SMTP. Confirma que MAIL_FROM_EMAIL coincide con un remitente habilitado. |
| Credenciales locales no funcionan | La nube nueva usa el administrador que configuraste, no los perfiles demo.local. |
| El primer acceso tarda | El plan Free despierta después de la inactividad; espera aproximadamente un minuto. |
| No aparecen estados nuevos | Abre cuentas o estados con una sesión de negocio/cliente; espera a que venza el intervalo de recuperación y actualiza. |
| Una imagen o una venta desaparece | Confirma que estás entrando al mismo servicio y a la misma base de Neon. Las imágenes actuales se guardan en la base, no en el disco efímero de Render. |
| Olvidaste la contraseña | No borres la base ni esperes que volver a poner BOOTSTRAP_ADMIN_PASSWORD la cambie. Solicita una recuperación controlada. |

## 13 Costos y límites

Según los planes consultados el 29 de octubre de 2026, Render tiene servicio web Free con suspensión tras 15 minutos de inactividad; Neon ofrece un plan Free con límites de almacenamiento y cómputo; Brevo incluye 300 correos diarios. Los planes pueden cambiar. Revisa el panel de cada proveedor y mantén seleccionados los planes gratuitos.

Render advierte que sus instancias gratuitas son para pruebas y proyectos personales. Esta configuración sirve para la exposición académica, sin disponibilidad continua garantizada. La aplicación y sus imágenes comparten el almacenamiento de Neon; usa imágenes pequeñas para conservar espacio. Brevo puede aceptar un correo y después retrasar su entrega por cuota o verificaciones, por lo que la aceptación de la API no garantiza recepción inmediata.

## 14 Fuentes oficiales

- [Docker en Render](https://render.com/docs/docker).
- [Límites gratuitos de Render](https://render.com/docs/free).
- [Variables automáticas y URL de Render](https://render.com/docs/environment-variables).
- [Blueprint render.yaml](https://render.com/docs/blueprint-spec).
- [Neon con SQLAlchemy](https://neon.com/docs/guides/sqlalchemy).
- [Precios de Neon](https://neon.com/pricing).
- [Envío transaccional por API de Brevo](https://developers.brevo.com/docs/send-a-transactional-email).
- [Remitentes y dominios de Brevo](https://developers.brevo.com/docs/getting-started-with-senders-and-domains).
- [Límites del plan gratuito de Brevo](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan).

## Alternativa con Blueprint

El paquete incluye `render.yaml`. Si prefieres esta ruta, crea **New → Blueprint**, conecta el repositorio y completa las variables privadas que Render solicite. No crees además otro Web Service: ambas rutas publican la misma aplicación. El archivo define únicamente un servicio web Free; no crea bases de pago ni procesos adicionales. La ruta manual de los apartados 5 y 6 permite revisar todos los campos antes de publicar.
