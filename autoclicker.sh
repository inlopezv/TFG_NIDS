#!/bin/bash
# Generador de patrones: Movimiento Snap + Disparo Sincronizado

WID=$(xdotool search --name "Xonotic" | head -n 1)
DURACION=300
# Limpieza al terminar
trap "xdotool keyup x w a s d; exit" INT TERM
( sleep $DURACION && kill -SIGTERM $$ ) &

echo "Generando datos de combate automatizado por 60s..."

while true; do
    # 1. EL SNAP (Movimiento de cámara instantáneo)
    # Generamos un salto brusco de mira
    X_SNAP=$(( ( RANDOM % 1000 ) - 500 ))
    Y_SNAP=$(( ( RANDOM % 400 ) - 200 ))
    xdotool mousemove_relative --sync -- $X_SNAP $Y_SNAP

    # 2. DISPARO INSTANTÁNEO (Anomalía de tiempo de reacción)
    # Un humano tiene un 'Reaction Time' de ~200ms tras apuntar.
    # El bot dispara en 0ms. Esta es la clave para tu detección.
    xdotool keydown x
    sleep 0.02  # Duración del clic perfectamente constante
    xdotool keyup x

    # 3. PATRÓN DE RÁFAGA (Burst fire inhumano)
    # Si quieres detectar disparos cadenciados:
    for i in {1..2}; do
        sleep 0.05
        xdotool key x
    done

    # 4. MOVIMIENTO DE EVASIÓN (AD-AD spam)
    # Los bots suelen strafear de forma rítmica para ser difíciles de dar.
    TECLA=$(shuf -e a d -n 1)
    xdotool keydown $TECLA
    sleep 0.1
    xdotool keyup $TECLA

    # Pausa entre "objetivos" simulados
    sleep 0.2
done