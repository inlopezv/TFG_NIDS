# TFG_NIDS: Sistema de Detección de Intrusiones en Tiempo Real para Videojuegos

## 📋 Descripción General

**TFG_NIDS** es un Sistema de Detección de Intrusiones (NIDS) basado en Machine Learning que analiza el tráfico de red y la telemetría de jugadores en tiempo real para detectar ataques maliciosos en sesiones de videojuegos (Xonotic), incluyendo:

- **Aimbot**: Detección de apuntado automático anómalo
- **Flood**: Detección de ataques de inundación de paquetes
- **LagSwitch**: Detección de manipulación de latencia
- **Normal**: Tráfico legítimo

---

## 🏗️ Arquitectura del Sistema

El proyecto está compuesto por tres componentes principales:

```
┌─────────────────────────────────────────────────────────────┐
│                    CONTENEDOR XONOTIC                       │
│  (Servidor de Juego + Mutators Compilados)                  │
│                                                              │
│  ✓ Servidor dedicado de Xonotic 0.8.6                       │
│  ✓ Puerto UDP 26000 (GamePort)                              │
│  ✓ Telemetría compilada (progs.dat + mutators)              │
│  ✓ Volumen compartido: /home/xonotic/Xonotic/              │
└─────────────────────────────────────────────────────────────┘
                              ↓↑
                    (Tráfico UDP Puerto 26000)
                              ↓↑
┌─────────────────────────────────────────────────────────────┐
│                  CONTENEDOR ZEEK (NIDS)                     │
│    (Captura de Tráfico + Análisis IA en Tiempo Real)        │
│                                                              │
│  ✓ Zeek IDS (análisis de paquetes)                          │
│  ✓ Tcpdump (captura PCAP de tráfico)                        │
│  ✓ Python + ML (modelos de detección)                       │
│  ✓ Volumen: /traffic_logs (resultados NIDS)                │
│  ✓ Volumen: /telemetria (datos de jugadores)               │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Estructura de Archivos del Repositorio

```
TFG_NIDS/
├── README.md                          # Este archivo
│
├── 🐳 DOCKERFILES (Configuración contenedores)
│   ├── Dockerfile.xonotic            # Servidor de juego Xonotic
│   └── Dockerfile.zeek               # NIDS + Análisis IA
│
├── 🎮 COMPONENTES DEL NIDS
│   ├── nids_live.py                  # Demonio principal (Python/IA en vivo)
│   ├── nids_window.zeek              # Script de Zeek (agregación de flujos)
│   └── nids_stream_live.csv          # Log en tiempo real de predicciones
│
├── 📊 DATOS Y LOGS
│   ├── traffic_logs/                 # Raíz de sesiones de juego
│   │   ├── {ETIQUETA}_{FECHA}/       # Carpeta por sesión (ej: "normal_20260504_173854/")
│   │   │   ├── pcap/                 # Capturas de red (PCAP)
│   │   │   │   ├── trafico_local.pcap        # Tráfico lado servidor (interfaz lo)
│   │   │   │   ├── trafico_amigo.pcap       # Tráfico lado cliente (interfaz tailscale0)
│   │   │   │   ├── errorserver_tcpdump.txt  # Logs de error tcpdump servidor
│   │   │   │   └── errorcliente_tcpdump.txt # Logs de error tcpdump cliente
│   │   │   │
│   │   │   └── zeek/                 # Logs de análisis Zeek
│   │   │       ├── nids_conn.log     # Flujos de conexión agregados cada 1 segundo
│   │   │       ├── loaded_scripts.log    # Scripts Zeek cargados
│   │   │       └── reporter.log      # Eventos y reportes Zeek
│   │   │
│   │   ├── alertas_nids.csv          # Log de alertas (timestamp, tipo_ataque, recuento)
│   │   └── nids_stream_live.csv      # Stream completo de predicciones
│   │
│   └── modelos/                      # Artefactos de Machine Learning
│       ├── manifiesto.pkl            # Configuración del modelo (tipo, features, umbrales)
│       ├── config.pkl                # Features utilizadas en entrenamiento
│       ├── scaler.pkl                # Escalador StandardScaler (normalización)
│       ├── modelo_ml.pkl             # Modelo ML (RF, XGB, SVM, etc)
│       │   O
│       ├── modelo_keras.keras        # Modelo Deep Learning (ANN, CNN, CNN_2D)
│       └── modelo_if.pkl             # Modelo Isolation Forest (opcional, si usa_if_consejero=True)
│
├── 📓 NOTEBOOKS (Análisis y Entrenamiento)
│   ├── ThisPruebaMalicioso_Random_V5.ipynb    # Notebook de análisis y validación
│   └── [otros notebooks de análisis]
│
├── 🔗 ENLACES A RECURSOS EXTERNOS
│   ├── Gráficas y Resultados
│   ├── Modelos Entrenados
│   └── Datasets
│
└── .gitignore                        # Excluye archivos de gran tamaño
```

---

## 🚀 Compilación e Instalación

### Paso 1: Compilar los Mutators de Xonotic (progs.dat)

Los mutators en Xonotic se programan en **QuakeC** y se compilan a bytecode en el archivo **`progs.dat`**.

#### A. Obtener el código fuente de Xonotic

```bash
# Descargar Xonotic con sus fuentes
wget https://dl.xonotic.org/xonotic-0.8.6.zip
unzip xonotic-0.8.6.zip
cd Xonotic
```

#### B. Ubicación de los mutators en el árbol de Xonotic

Los mutators se encuentran en:

```
Xonotic/source/qcsrc/server/mutators/
```

Estructura de mutators disponibles:
```
source/qcsrc/server/mutators/
├── _mod.qh              # Header principal de mutators
├── _registration.qh     # Sistema de registro
├── base/
├── default/
├── events/
├── gamemode_ctf/
├── gamemode_invasion/
├── mutators/            # ⭐ Aquí van tus mutators personalizados
│   ├── teleport_abuse.qc
│   ├── resource_control.qc
│   └── ...
└── [otros módulos]
```

#### C. Compilar los mutators

```bash
# Navegar a la carpeta de compilación
cd Xonotic
cd source

# Ejecutar el compilador QuakeC
./qcc                    # En Linux/macOS
# O
qcc.exe                  # En Windows

# Compilación típica (puede tardar 5-10 minutos)
make
```

**Resultado**: Se genera `progs.dat` en:
```
Xonotic/data/xonotic-data.pk3dir/progs.dat
```

O directamente en:
```
Xonotic/data/server/default.qc → progs.dat
```

#### D. Colocar progs.dat en Docker/Servidor

Existen dos opciones:

**OPCIÓN 1: Incluirlo en el volumen compartido (RECOMENDADO)**
```bash
# Copiar progs.dat a la carpeta de volumen Docker
cp Xonotic/data/server/progs.dat ./xonotic_volume/progs.dat

# Al levantar Docker:
docker-compose up -d --build
```

**OPCIÓN 2: Bakearlo en la imagen Docker**
```dockerfile
# Modificar Dockerfile.xonotic
COPY ./progs.dat /home/xonotic/Xonotic/data/server/
```

El servidor cargará automáticamente `progs.dat` desde:
```
/home/xonotic/Xonotic/data/server/progs.dat
```

---

### Paso 2: Compilar y Levantar con Docker Compose

#### Crear docker-compose.yml

```yaml
version: '3.8'

services:
  servidor_xonotic:
    build:
      context: .
      dockerfile: Dockerfile.xonotic
    container_name: servidor_xonotic
    ports:
      - "26000:26000/udp"
    volumes:
      - ./volumes/xonotic:/home/xonotic/Xonotic
    networks:
      - nids_net
    restart: unless-stopped

  zeek_xonotic_monitor:
    build:
      context: .
      dockerfile: Dockerfile.zeek
    container_name: zeek_xonotic_monitor
    depends_on:
      - servidor_xonotic
    volumes:
      - ./volumes/traffic_logs:/traffic_logs
      - ./volumes/telemetria:/telemetria
      - ./nids_live.py:/opt/nids_live.py
      - ./nids_window.zeek:/opt/nids_window.zeek
    networks:
      - nids_net
    restart: unless-stopped

networks:
  nids_net:
    driver: bridge
```

#### Ejecutar Todo con un Solo Comando

```bash
# Crear volúmenes locales si no existen
mkdir -p ./volumes/{xonotic,traffic_logs,telemetria}

# Compilar imágenes y levantar contenedores
docker-compose up -d --build

# Esperar a que estén listos (30-60 segundos)
sleep 30

# Verificar que están corriendo
docker-compose ps
```

**Resultado esperado:**
```
NAME                      COMMAND                  SERVICE                    STATUS
servidor_xonotic          "./xonotic-linux64-d…   servidor_xonotic           Up 2 minutes
zeek_xonotic_monitor      "/entrypoint.sh"         zeek_xonotic_monitor       Up 1 minute
```

---

## 📊 Generación de Datos

### 1. Datos de Telemetría

**¿Qué son?**: Datos en vivo del jugador (posición, ángulos, velocidad).

**Generados por**: El mutator compilado en `progs.dat` del servidor Xonotic.

**Ubicación**: 
```
/telemetria/
└── *telemetria*.csv    (archivo con timestamp, player_id, pitch, yaw, velocity, etc.)
```

**Formato CSV**:
```csv
timestamp,player_id,pos_x,pos_y,pos_z,pitch,yaw,is_attacking,velocity
1234567890.123,1,100.5,200.3,50.0,30.5,-45.2,1,250.5
1234567890.223,1,105.2,205.1,50.0,31.0,-46.1,0,248.3
1234567890.323,2,300.0,350.0,100.0,-10.5,120.3,1,180.0
```

**Sincronización**: Se obtiene del offset entre `timestamp_real = timestamp_game + OFFSET_GLOBAL`.

### 2. Datos de Red (PCAP y Zeek)

**¿Qué son?**: Tráfico UDP capturado entre servidor y cliente.

**Capturados por**: `tcpdump` en `Dockerfile.zeek`.

**Ubicación**:
```
/traffic_logs/{ETIQUETA}_{FECHA}/
├── pcap/
│   ├── trafico_local.pcap          # Servidor (interfaz lo)
│   └── trafico_amigo.pcap          # Cliente (interfaz tailscale0)
│
└── zeek/
    └── nids_conn.log               # Flujos agregados por segundo
```

**¿Dónde se generan exactamente?**

En `Dockerfile.zeek` (líneas 24-47):

```bash
CARPETA_SESION="/traffic_logs/${ETIQUETA}_${FECHA}"

# Se crea estructura:
mkdir -p $CARPETA_SESION/pcap
mkdir -p $CARPETA_SESION/zeek

# PCAP se escribe aquí:
tcpdump -U -p -i lo udp port 26000 -w $CARPETA_SESION/pcap/trafico_local.pcap
tcpdump -U -p -i tailscale0 udp port 26000 -w $CARPETA_SESION/pcap/trafico_amigo.pcap

# Zeek escribe análisis aquí:
zeek -C -i tailscale0 /opt/nids_window.zeek Log::default_logdir=$CARPETA_SESION/zeek
```

### 3. Descripción de Cada Fichero

| Fichero | Ubicación | Generado por | Contenido |
|---------|-----------|--------------|----------|
| **nids_conn.log** | `zeek/` | Zeek (nids_window.zeek) | Flujos de conexión agregados cada 1 segundo: timestamp, paquetes, bytes, PIAT (inter-arrival time), etc. |
| **trafico_local.pcap** | `pcap/` | tcpdump | Captura binaria de paquetes UDP desde servidor (interfaz loopback) |
| **trafico_amigo.pcap** | `pcap/` | tcpdump | Captura binaria de paquetes UDP desde cliente (interfaz Tailscale) |
| **alertas_nids.csv** | `/traffic_logs/` | nids_live.py | Log de alertas: timestamp, tipo_ataque (Aimbot/Flood/LagSwitch), recuento |
| **nids_stream_live.csv** | `/traffic_logs/` | nids_live.py | Stream completo: todas las filas predichas (telemetría + red + predicción) |
| ***telemetria*.csv** | `/telemetria/` | Servidor Xonotic | Datos de jugador: timestamp, player_id, ángulos, velocidad |
| **loaded_scripts.log** | `zeek/` | Zeek | Scripts cargados en esta sesión |
| **reporter.log** | `zeek/` | Zeek | Eventos y errores reportados |

---

## 🤖 Sistema de Detección en Tiempo Real (nids_live.py)

### Flujo de Ejecución

```
1. Lectura asíncrona de dos fuentes:
   ├─ Zeek (nids_conn.log): flujos de red cada 1 segundo
   └─ Telemetría (CSV): datos del jugador cada 0.1 segundos

2. Buffer circular (ventana deslizante de 30 segundos)

3. Cada 1 segundo:
   ├─ Agregar flujos Zeek + telemetría en ventana
   ├─ Calcular 60+ features (cinemática, red, estadísticas)
   ├─ Normalizar con StandardScaler
   ├─ Inyectar predicción Isolation Forest (si está habilitada)
   ├─ Inferencia con modelo ML/DL
   └─ Generar alertas si se detecta ataque

4. Outputs:
   ├─ alertas_nids.csv: solo anomalías
   └─ nids_stream_live.csv: todas las predicciones
```

### Configuración Clave

En `nids_live.py` (líneas 19-40):

```python
PATH_MODELOS = "/traffic_logs/modelos"           # Ubicación artefactos ML
BASE_PATH_LOGS = "/traffic_logs"                 # Logs de sesiones
BASE_PATH_TELEMETRIA = "/telemetria"             # Datos de jugador
ALERTAS_LOG = "/traffic_logs/alertas_nids.csv"   # ⭐ Alertas
STREAM_LOG = "/traffic_logs/nids_stream_live.csv" # ⭐ Stream vivo

TAMANO_VENTANA_SEC = 30.0                         # Ventana de análisis
INTERVALO_INFERENCIA_SEC = 1.0                    # Frecuencia predicción
RESOLUCION_FRAME_SEC = 0.1                        # Tick de telemetría

# Features inyectadas por Isolation Forest
IF_FEATURE_CANDIDATES = [
    'bidirectional_stddev_piat_ms',
    'src2dst_packets_sum',
    'bidirectional_bytes_sum',
    'delta_yaw',
    'vel_angular_yaw',
    ...
]
```

### Cargar Modelos

Los modelos se cargan desde `manifiesto.pkl`:

```python
manifiesto = joblib.load(os.path.join(PATH_MODELOS, "manifiesto.pkl"))
TIPO_MODELO = manifiesto.get('tipo_modelo', 'RF')  # 'RF', 'XGB', 'SVM', 'ANN', 'CNN', 'CNN_2D'
USA_IF_CONSEJERO = manifiesto.get('usa_if_consejero', True)
```

Artefactos esperados:
- `config.pkl`: lista de features
- `scaler.pkl`: StandardScaler
- `modelo_ml.pkl` o `modelo_keras.keras`: modelo principal
- `modelo_if.pkl`: Isolation Forest (opcional)

---

## 📈 Dónde se Generan los Datos

```
Sistema de Archivos del Contenedor:

/traffic_logs/                          (volumen Docker)
├── normal_20260504_173854/
│   ├── pcap/                           ← Captura PCAP (tcpdump)
│   │   ├── trafico_local.pcap
│   │   └── trafico_amigo.pcap
│   └── zeek/                           ← Análisis Zeek
│       ├── nids_conn.log               ← Flujos cada 1 segundo
│       ├── loaded_scripts.log
│       └── reporter.log
│
├── alertas_nids.csv                    ← Alertas globales (nids_live.py)
└── nids_stream_live.csv                ← Stream predicciones (nids_live.py)

/telemetria/                             (volumen Docker)
└── {nombre_archivo}_telemetria.csv     ← Datos jugadores (servidor Xonotic)

/traffic_logs/modelos/                   (modelos ML)
├── manifiesto.pkl
├── config.pkl
├── scaler.pkl
├── modelo_ml.pkl (o modelo_keras.keras)
└── modelo_if.pkl
```

---

## 📁 Secciones de Recursos Externos

### 🎨 Gráficas y Resultados

[📊 Ver Gráficas y Resultados en Google Drive](https://drive.google.com/drive/folders/1RIUt0ApblIUP2y2FD_d3it5bVIDX2lmP?usp=sharing)

Contenido esperado:
- Matrices de confusión por clase
- Curvas ROC-AUC
- Rendimiento por tipo de ataque
- Distribuciones de features
- Análisis temporal de alertas

### 🤖 Modelos Entrenados

[🤖 Ver Modelos Entrenados en Google Drive](https://drive.google.com/drive/folders/1GoTs4_Ye4AezjB4QholQI9GubWYFooPC?usp=sharing)

Contenido esperado:
- `rf_model_v3.pkl` (Random Forest)
- `xgb_model_v3.pkl` (XGBoost)
- `cnn_model_v3.keras` (CNN TensorFlow)
- `ann_model_v3.keras` (ANN)
- `manifiesto_v3.pkl` (configuración)

### 📊 Datasets

[📁 Ver Datasets en Google Drive](https://drive.google.com/drive/folders/1M_WdyhWaNMOPdtljqj3o_8pha0RAC0Re?usp=sharing)

Contenido esperado:
- `dataset_entrenamiento_v3.csv` (Train)
- `dataset_validacion_v3.csv` (Val)
- `dataset_test_v3.csv` (Test)
- Descripción de features
- Distribución de clases

---

## 🔍 Monitoreo en Vivo

### Verificar Logs de Ejecución

```bash
# NIDS (IA en tiempo real)
docker logs -f zeek_xonotic_monitor

# Xonotic (servidor de juego)
docker logs -f servidor_xonotic
```

---

## 📚 Referencias

- [Documentación Xonotic](https://xonotic.org/)
- [QuakeC Manual](https://www.quakewiki.net/)
- [Zeek Documentation](https://docs.zeek.org/)
- [TensorFlow Keras](https://www.tensorflow.org/guide/keras)
- [Scikit-Learn](https://scikit-learn.org/)

---

## 👤 Autor

**inlopezv** - Trabajo de Fin de Grado (TFG)

---

**Última actualización**: 2026-09-08
