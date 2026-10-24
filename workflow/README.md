# workflow-ia

Workflow serverless en AWS que evalua archivos markdown usando un API de Agente IA generica, guarda resultados en DynamoDB, crea un reporte CSV comparativo (separado por `;`) en S3 y envia el reporte por correo con SendGrid.

## Funcionalidades

- Expone un endpoint `POST /workflow` en API Gateway (HTTP API) para iniciar el proceso de forma asincrona.
- Recibe como entrada:
  - `instructions_s3_link`: archivo markdown con instrucciones para IA.
  - `content_s3_folder_link`: carpeta S3 con archivos markdown a evaluar.
  - `email`: correo destino para enviar resultados.
- Ejecuta un workflow en Step Functions con los pasos:
  1. Listar archivos markdown dentro de la carpeta S3.
  2. Evaluar cada archivo llamando al API Agente IA generica.
  3. Guardar cada resultado JSON en DynamoDB.
  4. Generar un archivo CSV con tabla comparativa (campos separados por `;`) y codificacion `UTF-8 con BOM` para soportar caracteres en espanol, y guardarlo en `s3://<bucket>/resultados/...`.
  5. Enviar correo con SendGrid adjuntando el CSV generado.

## Arquitectura

- AWS API Gateway HTTP API
- AWS Lambda (Python 3.14)
- AWS Step Functions
- AWS DynamoDB
- AWS S3
- SendGrid API (`/v3/mail/send`)
- Serverless Framework v4
- Rol IAM existente: `LabRole`

## Estructura del proyecto

- `serverless.yml`: IaC completa (API, Lambdas, DynamoDB, Step Functions).
- `handler.py`: logica de las Lambdas del workflow.
- `workflow.postman_collection.json`: coleccion Postman para pruebas.
- `prompt.md`: prompt de referencia.

## Contrato del API

### Endpoint

- Metodo: `POST`
- Ruta: `/workflow`
- Content-Type: `application/json`

### Body de entrada

```json
{
  "instructions_s3_link": "s3://mi-bucket/instrucciones.md",
  "content_s3_folder_link": "s3://mi-bucket/contenido/",
  "email": "usuario@dominio.com"
}
```

### Respuesta exitosa

- HTTP `202`
- Inicia el workflow de manera asincrona.
- Devuelve `executionArn` y `executionName`.

### Respuestas de error

- HTTP `400`: body invalido o campos faltantes.
- HTTP `502`: error iniciando Step Functions.

## Variables de entorno requeridas

- `AGENTE_IA_API_URL`: endpoint desplegado del API `agente-ia-generica`.
- `SENDGRID_API_KEY`: API key de SendGrid.
- `SENDGRID_FROM_EMAIL`: correo remitente validado en SendGrid.
- `SENDGRID_FROM_NAME`: nombre remitente (opcional, default `Workflow IA`).

## Despliegue automatico (Serverless Framework v4)

1. Autentica Serverless Framework:

```bash
serverless login
```

2. Configura credenciales AWS en tu entorno (.aws/credentials)

3. Define variables de entorno (Bash):

```bash
export AGENTE_IA_API_URL="https://<api-id>.execute-api.us-east-1.amazonaws.com/agente-ia-generica"
export SENDGRID_API_KEY="tu_sendgrid_api_key"
export SENDGRID_FROM_EMAIL="tu-correo-validado@dominio.com"
export SENDGRID_FROM_NAME="Workflow IA"
```

4. Despliega:

```bash
serverless deploy
```

5. (Opcional) Elimina recursos:

```bash
serverless remove
```

## Prueba rapida con curl

```bash
curl -X POST "https://<api-id>.execute-api.us-east-1.amazonaws.com/workflow" \
  -H "Content-Type: application/json" \
  -d '{
    "instructions_s3_link": "s3://mi-bucket/instrucciones.md",
    "content_s3_folder_link": "s3://mi-bucket/contenido/",
    "email": "usuario@dominio.com"
  }'
```

## Coleccion Postman

Importa `workflow.postman_collection.json`.

Configura la variable `baseUrl` con el endpoint base, por ejemplo:

- `https://<api-id>.execute-api.us-east-1.amazonaws.com`

## Metadatos de creacion

- Creado con GitHub Copilot
- Modelo LLM utilizado: GPT-5.3-Codex
- Fecha de creacion: 2026-03-06

## Referencia del prompt utilizado

```md
## Rol / Persona
Actua como un experto en crear Agentes de IA con servicios de AWS

## Contexto
Se necesita construir un Workflow que use IA y que sea completamente serverless

## Tarea / Objetivo 
Crea un workflow que use IA con estas funcionalidades:
- Pasos:
  1. Recibe como entrada estos datos:
  - Ruta a archivo en bucket S3 en formato markdown con instrucciones para IA
  - Ruta a carpeta en bucket S3 que contenga archivos en formato markdown para evaluar con las instrucciones 
  - Correo donde enviar el archivo con los resultados
  2. Por cada archivo debe llamar al Api Agente IA generica y enviarle como parametro la ruta del archivo de instrucciones y la ruta del archivo de contenido.
  3. El resultado del Api Agente IA generica (formato json) debe guardarlo en una tabla dynamodb.
  4. Debe generar un archivo en formato CSV con campos separados por punto y coma (;) y una tabla comparativa con el resultado del Api de todos los archivos evaluados, almacenarlo en el bucket en una carpeta "resultados".
  5. Debe enviar un correo utilizando el Api de SendGrid adjuntando el archivo CSV anterior.

## Requisitos de la respuesta
- Para la IaC (Infraestructura como codigo) utiliza el framework serverless version 4 con rol de IAM LabRole existente.
- Para el workflow utiliza:
  - Servicios de AWS (Api Gateway, Step Functions, DynamoDB, Lambda). Genera un endpoint en Api Gateway para poder ejecutar el workflow Step Functions de forma asincrona.
  - En caso se necesite crear lambdas utiliza lenguaje de programacion python version 3.14 con libreria urllib en vez de requests en caso se necesite.
- Genera un readme.md con las funcionalidades que contiene y las instrucciones para hacer el despliegue automatico. Adicionalmente indica explicitamente que ha sido creado con GitHub Copilot, el modelo LLM usado, la fecha de creacion e incluye como referencia todo el texto del prompt utilizado.
- Genera una coleccion postman para poder probar el nuevo api creado.

## Elementos adicionales
-
```
