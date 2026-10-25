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
  2. Por cada archivo debe llamar al Api Agente IA generica y enviarle como parametro la ruta del archivo de instrucciones y la ruta del archivo de contenido.
  3. El resultado del Api Agente IA generica (formato json) debe guardarlo en una tabla dynamodb.
  4. Debe generar un archivo en formato CSV con campos separados por punto y coma (;) y una tabla comparativa con el resultado del Api de todos los archivos evaluados, almacenarlo en el bucket en una carpeta "resultados".

## Requisitos de la respuesta
- Para la IaC (Infraestructura como codigo) utiliza el framework serverless version 4 con rol de IAM LabRole existente.
- Para el workflow utiliza:
  - Servicios de AWS (Api Gateway, Step Functions, DynamoDB, Lambda). Genera un endpoint en Api Gateway para poder ejecutar el workflow Step Functions de forma asincrona.
  - En caso se necesite crear lambdas utiliza lenguaje de programacion python version 3.14 con libreria urllib en vez de requests en caso se necesite.
- Genera un readme.md con las funcionalidades que contiene y las instrucciones para hacer el despliegue automatico. Adicionalmente indica explicitamente que ha sido creado con GitHub Copilot, el modelo LLM usado, la fecha de creacion e incluye como referencia todo el texto del prompt utilizado.
- Genera una coleccion postman para poder probar el nuevo api creado.

## Elementos adicionales
-