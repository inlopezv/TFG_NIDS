# Usamos una imagen base ligera de Debian
FROM debian:bullseye-slim

# Evitar ventanas interactivas durante la instalación
ENV DEBIAN_FRONTEND=noninteractive

# Instalar dependencias: wget (descargar), unzip (extraer), ca-certificates (HTTPS)
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Por seguridad, creamos un usuario llamado 'xonotic' en lugar de usar 'root'
RUN useradd -m xonotic
USER xonotic
WORKDIR /home/xonotic

# Descargar el juego y descomprimirlo
RUN wget https://dl.xonotic.org/xonotic-0.8.6.zip -O xonotic.zip && \
    unzip xonotic.zip && \
    rm xonotic.zip

# Entrar a la carpeta del juego
WORKDIR /home/xonotic/Xonotic

# Exponer el puerto por defecto del servidor de Xonotic (UDP)
EXPOSE 26000/udp

# El comando que ejecutará el contenedor al encenderse
CMD /bin/bash -c "rm -f /home/xonotic/.xonotic/lock* && exec ./xonotic-linux64-dedicated -sessionid kaliserver"
