# CIENCIA DE DATOS APLICADA AL MERCADO AUTOMOVILISTICO

Pipeline de ingenieria y ciencia de datos sobre el mercado espanol de vehiculos de segunda mano, a partir de anuncios extraidos de coches.net.

Trabajo de Fin de Grado (TFG) — Grado en Ingenieria Informatica.

---

## Autoria

| Campo | Valor |
|---|---|
| Autor | Jose Manuel Escribano Villena |
| Titulacion | Grado en Ingenieria Informática |
| Tipo de trabajo | Trabajo de Fin de Grado (TFG) |
| Centro | Universidad de Alicante |
| Tutores | David Tomas, Olga Frances Hernandez|
| Curso academico | 2025-2026 |

---

## Disclaimer de responsabilidad

Proyecto desarrollado con fines academicos en el marco de un Trabajo de Fin de Grado. La extraccion se realizo respetando limites de carga razonables. Conviene revisar los terminos de uso del sitio fuente antes de reutilizar el codigo.

---

## Descripcion

El proyecto implementa un flujo de datos de extremo a extremo sobre el mercado de vehiculos de ocasion. Parte de la extraccion automatizada de aproximadamente 25.000 anuncios y recorre las fases de almacenamiento, transformacion, modelado y visualizacion.

Fases del pipeline:

1. Extraccion (scraping) de anuncios mediante un scraper sigiloso basado en Camoufox/Playwright.
2. Persistencia en bruto como ficheros JSON (uno por anuncio) y carga en PostgreSQL.
3. Transformacion analitica con dbt siguiendo el patron staging -> intermediate -> marts.
4. Analisis y modelado: exploracion (EDA), Machine Learning y NLP sobre las descripciones.

---

## Arquitectura

```
coches.net  ->  scrapper_coches.py  ->  data/ (JSON)  ->  insert_ads  ->  PostgreSQL
                                                                              |

                  v                       v                       v          
            analisis_coches          ml_coches            nlp_coches_     
              (EDA)                   (Machine Learning)   comments (NLP)  
                                          |                     |
                                          v                     v
                                  features (CSV)        comments_features.csv
                                  (Feature Store ML)    (Feature Store NLP)
```

---

## Estructura del proyecto

```
.
├── README.md
├── installation                  # Script de instalacion y preparacion del entorno
├── scrapper_coches.py            # Scraper principal (Camoufox/Playwright)
├── insert_ads                    # Carga de los JSON en PostgreSQL (UPSERT)
│
├── config/
│   ├── db_config.json            # Credenciales de PostgreSQL
│   └── state.json                # Estado de sesion del scraper (marca/pagina)
│
├── data/                         # Anuncios extraidos en JSON (1 fichero por anuncio)
│   ├── 70234824.json
│   ├── 70235236.json
│   └── ...
│
├── notebooks/
│── analisis_coches.ipynb     # Analisis exploratorio (EDA)
│── ml_coches.ipynb           # Modelos de Machine Learning
│── nlp_coches_comments.ipynb # Analisis NLP de los comentarios
│
├── features/
│── anuncios.csv              # Dataset consolidado de partida
│── features.csv              # Feature Store derivado del pipeline ML
│── comments_features.csv     # Feature Store derivado del pipeline NLP
```

---

## Descripcion de los archivos

### scrapper_coches.py
Motor de extraccion del proyecto. Scraper asincrono construido sobre Camoufox (variante sigilosa de Firefox) y Playwright. Migrado desde una version anterior por problemas de bloqueo. Sus responsabilidades:

- Navegar coches.net simulando comportamiento humano (delays log-normales, scroll con retrocesos, movimientos de raton, pausas largas).
- Persistir cada anuncio como JSON en `data/`, evitando sobrescribir datos mas completos.
- Reanudar el trabajo entre ejecuciones mediante `config/state.json`.
- Detectar bloqueos (captcha, paginas de error) y anuncios no disponibles.

Ofrece un menu con varios modos: scraping basico (listados), scraping extendido (entra a cada anuncio y navega con "Siguiente"), completar anuncios pendientes, configuracion de tiempos y una opcion de carga en base de datos. Incluye normalizadores de precio, kilometraje, potencia, cilindrada, transmision, puertas y plazas, ademas del reconocimiento de la marca a partir del modelo.

### insert_ads
Carga masiva de los anuncios extraidos en PostgreSQL. Recorre los ficheros JSON de `data/`, selecciona los anuncios con estado extendido (`extendido = "S"`), completa la ubicacion a partir de la URL cuando falta y los inserta por lotes. La insercion usa UPSERT (`ON CONFLICT (id) DO UPDATE`), de modo que reejecutarlo actualiza precio y kilometraje sin duplicar registros. Crea la tabla `anuncios` y sus indices si no existen, e imprime estadisticas de carga (total, precio medio, marcas unicas). Corresponde a la logica de carga (clase `CochesDBLoader`) que tambien puede invocarse desde el scraper.

### installation
Script de preparacion del entorno. Automatiza la instalacion de dependencias necesarias para ejecutar el proyecto: Camoufox y su descarga de binarios, Playwright, el conector de PostgreSQL y las librerias de analisis (pandas, scikit-learn, etc.). Sirve como punto de entrada reproducible para dejar el entorno listo antes de lanzar el scraper o los notebooks.

### analisis_coches (EDA)
Notebook de analisis exploratorio. Carga el dataset consolidado y aplica una segmentacion de mercado en tres niveles. Caracteristicas metodologicas:

- Filtrado de valores atipicos por percentiles P2-P98 por grafico, en lugar de borrado global de filas, para preservar la integridad del dataset.
- Uso de la mediana sobre la media en variables economicas sesgadas.
- Variable derivada de antiguedad y visualizaciones sobre precio, antiguedad, kilometraje y composicion por segmento.

Segmentacion de mercado utilizada:

| Nivel | Descripcion |
|---|---|
| Utilitario | Gama de acceso / uso diario |
| Plus | Gama media |
| Premium | Gama alta y vehiculos singulares (marcas premium o precio por encima del umbral dinamico P97) |

### ml_coches (Machine Learning)
Notebook con el pipeline de modelado supervisado y no supervisado. Cubre cuatro tareas, con preferencia por modelos basados en arboles para datos tabulares:

| Tarea | Modelo |
|---|---|
| Prediccion de precio (regresion) | RandomForestRegressor |
| Clasificacion de segmento (sin usar la marca) | HistGradientBoostingClassifier |
| Deteccion de anomalias | IsolationForest + z-score de residuos |
| Clustering | KMeans (k = 5) |

El notebook genera el Feature Store tabular consumido por las fases posteriores.

### nlp_coches_comments (NLP)
Notebook de procesamiento de lenguaje natural sobre el campo de comentarios del vendedor. Incluye:

- Vectorizacion TF-IDF del corpus de descripciones y analisis diferencial por segmento.
- Modelado de temas con LDA. El etiquetado de los topicos se realiza de forma manual mediante diccionario, dado que el orden de los topicos no es determinista entre ejecuciones.
- Extraccion de variables booleanas mediante expresiones regulares (ITV, estado, equipamiento, etc.), elegidas frente a extraccion por LLM por su reproducibilidad.

Exporta el Feature Store de comentarios.

### CSV con las features
Artefactos de salida que constituyen el Feature Store del proyecto:

- `anuncios.csv`: dataset consolidado de partida que alimenta el EDA. Se coloca junto al notebook en tiempo de ejecucion.
- `features.csv`: tabla de caracteristicas derivada del pipeline de Machine Learning (variables numericas, segmento, predicciones y senalizacion de anomalias). Sirve de entrada para el dashboard y la capa analitica.
- `comments_features.csv`: tabla de caracteristicas derivada del pipeline NLP, con las variables extraidas por regex y la informacion de topicos por anuncio.

Estos ficheros desacoplan el calculo de caracteristicas de su consumo, de modo que el dashboard y las capas posteriores trabajan sobre datos ya procesados y reproducibles.

---

## Modelo de datos

Cada anuncio se almacena como JSON y se carga en la tabla `anuncios`. Campos principales:

| Campo | Tipo | Descripcion |
|---|---|---|
| id | VARCHAR (PK) | Identificador del anuncio |
| brand | VARCHAR | Marca normalizada |
| model | VARCHAR | Modelo (texto original) |
| price | INTEGER | Precio actual en euros |
| original_price | INTEGER | Precio nuevo sin extras (si disponible) |
| year | INTEGER | Ano de matriculacion |
| km | INTEGER | Kilometraje |
| cv | INTEGER | Potencia en CV |
| cc | INTEGER | Cilindrada en cc |
| fuel | VARCHAR | Combustible |
| transmission | VARCHAR | Manual / Automatico |
| doors | INTEGER | Numero de puertas |
| seats | INTEGER | Numero de plazas |
| car_type | VARCHAR | Tipo de carroceria |
| location | VARCHAR | Provincia (extraida de la URL) |
| label | VARCHAR | Etiqueta medioambiental DGT |
| comments | TEXT | Descripcion libre del vendedor |
| url | VARCHAR | URL del anuncio |
| extendido | VARCHAR | Estado: N / S / NO DISPONIBLE |

---

## Requisitos y ejecucion

Preparacion del entorno (mediante el script de instalacion o de forma manual):

```bash
python installation.py
```

Credenciales de base de datos en `config/db_config.json` (no versionar):

```json
{ "password": "PASSWORD_POSTGRES" }
```

Ejecucion:

```bash
# Scraper (menu interactivo)
python scrapper_coches.py

# Carga de anuncios en PostgreSQL
python insert_ads

# Notebooks de analisis
jupyter notebook notebooks/
```

---

## Stack tecnologico

| Capa | Tecnologias |
|---|---|
| Scraping | Camoufox, Playwright, asyncio |
| Almacenamiento | PostgreSQL, ficheros JSON |
| Transformacion | dbt, Python |
| Machine Learning | scikit-learn (RandomForest, HistGradientBoosting, IsolationForest, KMeans) |
| NLP | TF-IDF, LDA, expresiones regulares |
| Visualizacion | Metabase o Apache Superset |
| Analisis | pandas, numpy, seaborn, matplotlib |

---

