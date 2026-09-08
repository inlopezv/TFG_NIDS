# Usamos una imagen base ligera de Debian
FROM zeek/zeek:latest

# Instalar dependencias
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    ca-certificates \
    tcpdump \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages \
    pandas numpy scikit-learn scipy joblib xgboost tensorflow psutil

ENV PYTHONUNBUFFERED=1

COPY nids_live.py /opt/nids_live.py
COPY nids_window.zeek /opt/nids_window.zeek

# Creamos el script de arranque modificado
RUN echo '#!/bin/bash\n\
# 1. Generamos la marca de tiempo (AñoMesDia_HoraMinutoSegundo)\n\
FECHA=$(date +"%Y%m%d_%H%M%S")\n\
\n\
# Leemos la variable de entorno ETIQUETA \n\
ETIQUETA=${ETIQUETA:-"sin_clasificar"}\n\
CARPETA_SESION="/traffic_logs/${ETIQUETA}_${FECHA}"\n\
\n\
echo "=> Creando estructura de carpetas para la sesion: $FECHA"\n\
mkdir -p $CARPETA_SESION/pcap\n\
mkdir -p $CARPETA_SESION/zeek\n\
\n\
echo "=> Iniciando capturas crudas con tcpdump en segundo plano..."\n\
# CAPTURA 1: Tráfico del Host (Tú) en la interfaz local\n\
tcpdump -U -p -i lo udp port 26000 -w $CARPETA_SESION/pcap/trafico_local.pcap 2> $CARPETA_SESION/pcap/errorserver_tcpdump.txt &\n\
\n\
# CAPTURA 2: Tráfico del Cliente (Tu amigo) en la interfaz de Tailscale\n\
tcpdump -U -p -i tailscale0 udp port 26000 -w $CARPETA_SESION/pcap/trafico_amigo.pcap 2> $CARPETA_SESION/pcap/errorcliente_tcpdump.txt &\n\
\n\
echo "=> Iniciando analisis en vivo con Zeek..."\n\
zeek -C -i tailscale0 /opt/nids_window.zeek Log::default_logdir=$CARPETA_SESION/zeek Log::default_rotation_interval=0sec Log::flush_interval=1sec local &\n\
ZEEK_PID=$!\n\
echo "=> Zeek iniciado en tailscale0 con PID $ZEEK_PID"\n\
echo "=> Iniciando Demonio NIDS (IA) en tiempo real..."\n\
python3 -u /opt/nids_live.py\n\
' > /entrypoint.sh

# Le damos permisos de ejecución al script
RUN chmod +x /entrypoint.sh

# Declaramos el volumen
VOLUME ["/traffic_logs"]

# Le decimos al contenedor que ejecute nuestro script al encenderse
CMD ["/entrypoint.sh"]