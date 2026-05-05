# Usamos una imagen base ligera de Debian
FROM zeek/zeek:latest

# Instalar dependencias: wget (descargar), unzip (extraer), ca-certificates (HTTPS)
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    ca-certificates \
    tcpdump \
    && rm -rf /var/lib/apt/lists/*

# 4. Creamos el script de arranque
# - tcpdump graba el puerto 26000 y lo manda al fondo con el símbolo '&'
# - zeek escucha en la tarjeta de red 'eth0' y guarda sus logs en /capturas

# RUN echo '#!/bin/bash\n\
# echo "=> Iniciando captura cruda con tcpdump en segundo plano..."\n\
# tcpdump -p -i any udp port 26000 -w /logs/captura_cruda.pcap &\n\
# \n\
# echo "=> Iniciando análisis en vivo con Zeek..."\n\
# zeek -C -i eth0 Log::default_logdir=/logs local\n\
# ' > /entrypoint.sh

RUN echo '#!/bin/bash\n\
# 1. Generamos la marca de tiempo (AñoMesDia_HoraMinutoSegundo)\n\
FECHA=$(date +"%Y%m%d_%H%M%S")\n\
\n\
#Leemos la variable de entorno ETIQUETA 
ETIQUETA=${ETIQUETA:-"sin_clasificar"}\n\
CARPETA_SESION="/traffic_logs/${ETIQUETA}_${FECHA}"\n\
echo "=> Creando estructura de carpetas para la sesion: $FECHA"\n\
# Creamos la carpeta principal de la sesión y sus dos subcarpetas\n\
mkdir -p $CARPETA_SESION/pcap\n\
mkdir -p $CARPETA_SESION/zeek\n\
\n\
echo "=> Iniciando captura cruda con tcpdump en segundo plano..."\n\
# Guardamos el pcap dentro de su subcarpeta correspondiente\n\
tcpdump -U -p -i any udp port 26000 -w $CARPETA_SESION/pcap/trafico_crudo.pcap &\n\
\n\
echo "=> Iniciando analisis en vivo con Zeek..."\n\
# Obligamos a Zeek a meter todos sus logs (.log) en su subcarpeta\n\
zeek -C -i eth0 Log::default_logdir=$CARPETA_SESION/zeek local\n\
' > /entrypoint.sh

# 5. Le damos permisos de ejecución al script
RUN chmod +x /entrypoint.sh

# 6. Declaramos el volumen (el puente entre el contenedor y tu ordenador)
VOLUME ["/traffic_logs"]

# 7. Le decimos al contenedor que ejecute nuestro script al encenderse
CMD ["/entrypoint.sh"]


