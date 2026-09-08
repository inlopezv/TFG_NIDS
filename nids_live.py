import os
import time
import threading
import glob
import joblib
import numpy as np
import pandas as pd
import math
import re
import warnings
from datetime import datetime
from collections import deque

warnings.filterwarnings('ignore', category=pd.errors.PerformanceWarning)

# =====================================================================
# CONFIGURACIÓN PARA DOCKER
# =====================================================================
PATH_MODELOS = "/traffic_logs/modelos"
BASE_PATH_LOGS = "/traffic_logs"
BASE_PATH_TELEMETRIA = "/telemetria"
ALERTAS_LOG = "/traffic_logs/alertas_nids.csv"
STREAM_LOG = "/traffic_logs/nids_stream_live.csv"

TAMANO_VENTANA_SEC = 30.0
INTERVALO_INFERENCIA_SEC = 1.0
RESOLUCION_FRAME_SEC = 0.1

OFFSET_GLOBAL = 0.0
LECTURA_ESTADISTICAS = {}
IF_FEATURE_CANDIDATES = [
    'bidirectional_stddev_piat_ms',
    'src2dst_packets_sum',
    'bidirectional_bytes_sum',
    'delta_yaw',
    'vel_angular_yaw',
    'src2dst_packets_sum_roll_max_5',
    'bidirectional_bytes_sum_roll_max_5',
    'bidirectional_mean_piat_ms_roll_std_5',
]

# =====================================================================
# LECTURA DEL MANIFIESTO (MLOps)
# =====================================================================
print("\n[NIDS-INIT] Arrancando demonio de seguridad...")
try:
    manifiesto = joblib.load(os.path.join(PATH_MODELOS, "manifiesto.pkl"))
    USA_IF_CONSEJERO = manifiesto.get('usa_if_consejero', True)
    TIPO_MODELO = manifiesto.get('tipo_modelo', 'RF')
    
    config = joblib.load(os.path.join(PATH_MODELOS, "config.pkl"))
    features_base = config['features']
    umbrales = config.get('thresholds', {})
    scaler = joblib.load(os.path.join(PATH_MODELOS, "scaler.pkl"))
    
    if USA_IF_CONSEJERO:
        modelo_if = joblib.load(os.path.join(PATH_MODELOS, "modelo_if.pkl"))
    
    if TIPO_MODELO in ['ANN', 'CNN', 'CNN_2D']:
        from tensorflow.keras.models import load_model
        modelo_principal = load_model(os.path.join(PATH_MODELOS, "modelo_keras.keras"))
    else:
        modelo_principal = joblib.load(os.path.join(PATH_MODELOS, "modelo_ml.pkl"))
        
    print(f"[NIDS-INIT] Artefactos IA listos. Modelo: {TIPO_MODELO}")

except Exception as e:
    print(f"[NIDS-ERROR CRÍTICO] Fallo en la carga de modelos: {e}")
    exit(1)

# =====================================================================
# GESTIÓN DE BÚFERES
# =====================================================================
class NIDSRealTimeBuffer:
    def __init__(self, max_duration=TAMANO_VENTANA_SEC):
        self.max_duration = max_duration
        self.buffer_red = deque()
        self.buffer_telemetria = deque()
        self.lock = threading.Lock()

    def limpiar_obsoletos(self, timestamp_actual):
        limite = timestamp_actual - self.max_duration
        with self.lock:
            while self.buffer_red and self.buffer_red[0]['timestamp'] < limite:
                self.buffer_red.popleft()
            while self.buffer_telemetria and self.buffer_telemetria[0]['timestamp'] < limite:
                self.buffer_telemetria.popleft()

    def agregar_red(self, dato):
        with self.lock: self.buffer_red.append(dato)

    def agregar_telemetria(self, dato):
        with self.lock: self.buffer_telemetria.append(dato)

    def obtener_dataframes(self):
        with self.lock:
            return pd.DataFrame(list(self.buffer_red)), pd.DataFrame(list(self.buffer_telemetria))

buffer_global = NIDSRealTimeBuffer()

# =====================================================================
# RASTREADORES DINÁMICOS
# =====================================================================
def actualizar_offset_desde_archivo(ruta_telemetria):
    global OFFSET_GLOBAL
    # El mutator actual no escribe un archivo de sincronizacion fiable por
    # partida. El offset se calibra con la primera fila del CSV activo.
    OFFSET_GLOBAL = 0.0

def obtener_ultimo_log_zeek(base_path):
    archivos = glob.glob(os.path.join(base_path, "*", "zeek", "nids_conn.log"))
    return max(
        archivos,
        key=lambda ruta: marca_temporal_archivo(os.path.dirname(os.path.dirname(ruta)))
    ) if archivos else None

def obtener_ultima_telemetria(base_path):
    archivos = glob.glob(os.path.join(base_path, "**", "*telemetria*.csv"), recursive=True)
    if not archivos:
        return None
    archivos_con_datos = [ruta for ruta in archivos if tiene_datos_telemetria(ruta)]
    return max(archivos_con_datos, key=marca_temporal_archivo) if archivos_con_datos else None

def tiene_datos_telemetria(ruta):
    """Ignora CSV recién creados que todavía solo contienen la cabecera."""
    try:
        with open(ruta, 'r', encoding='utf-8', errors='replace') as archivo:
            for linea in archivo:
                linea = linea.lstrip('\ufeff').strip()
                if linea and not linea.lower().startswith('timestamp,'):
                    return len(linea.split(',')) >= 9
    except OSError:
        pass
    return False

def diagnostico_fuentes(base_path):
    return None

def marca_temporal_archivo(ruta):
    """Usa la fecha del nombre y deja mtime como respaldo."""
    nombre = os.path.basename(ruta)
    patrones = (
        r"(\d{8})[_-](\d{6})",
        r"(\d{4}-\d{2}-\d{2})[_-](\d{2})[-:](\d{2})[-:](\d{2})",
    )
    for indice, patron in enumerate(patrones):
        coincidencia = re.search(patron, nombre)
        if not coincidencia:
            continue
        try:
            if indice == 0:
                return datetime.strptime(
                    f"{coincidencia.group(1)}_{coincidencia.group(2)}", "%Y%m%d_%H%M%S"
                ).timestamp()
            return datetime.strptime(
                "_".join(coincidencia.groups()), "%Y-%m-%d_%H_%M_%S"
            ).timestamp()
        except ValueError:
            pass
    return os.path.getmtime(ruta)

def rastreador_dinamico(base_path, funcion_busqueda, parser, callback, tipo, on_new_file=None):
    archivo_actual = None
    f = None
    ino_actual = None
    lineas_leidas = 0
    lineas_aceptadas = 0
    ultimo_reporte = time.time()
    print(f"[RADAR] Buscando archivos de {tipo} en {base_path}...")
    
    while True:
        nuevo_archivo = funcion_busqueda(base_path)
        if nuevo_archivo and nuevo_archivo != archivo_actual:
            if f: f.close()
            print(f"[NIDS-RELOAD] 🔗 Conectado a {tipo}: {os.path.basename(nuevo_archivo)}")
            archivo_actual = nuevo_archivo
            
            if on_new_file:
                on_new_file(archivo_actual)
                
            # Procesar también lo que ya estaba escrito y después seguir el archivo.
            f = open(archivo_actual, 'r', encoding='utf-8', errors='replace')
            ino_actual = os.stat(archivo_actual).st_ino
        
        if not f:
            time.sleep(1)
            continue
            
        linea = f.readline()
        if not linea:
            time.sleep(0.05)
            try:
                if os.stat(archivo_actual).st_ino != ino_actual or os.stat(archivo_actual).st_size < f.tell():
                    f.close()
                    f = open(archivo_actual, 'r', encoding='utf-8', errors='replace')
                    ino_actual = os.stat(archivo_actual).st_ino
            except FileNotFoundError: pass
            continue
            
        dato = parser(linea)
        lineas_leidas += 1
        if dato:
            lineas_aceptadas += 1
            callback(dato)
        if time.time() - ultimo_reporte >= 10.0:
            LECTURA_ESTADISTICAS[tipo] = (lineas_leidas, lineas_aceptadas)
            print(
                f"[NIDS-LECTURA] {tipo} | leidas={lineas_leidas} "
                f"| aceptadas={lineas_aceptadas}"
            )
            ultimo_reporte = time.time()

# =====================================================================
# PARSERS DE DATOS
# =====================================================================
def parsear_linea_zeek(linea):
    linea = linea.lstrip('\ufeff').strip()
    if linea.startswith('#') or not linea: return None
    # El escritor ASCII de Zeek usa TSV, pero split() también acepta espacios
    # si la imagen/configuración cambia el separador del escritor.
    partes = linea.split()
    try:
        # nids_window.zeek emite una fila por flujo y segundo, ya agregada.
        if len(partes) < 11:
            return None
        valores = [0.0 if valor == '-' else float(valor) for valor in partes[:11]]
        ts, orig_p, resp_p, orig_b, resp_b, total_bytes, dur = valores[:7]
        mean_piat, std_piat, mean_ps, std_ps = valores[7:]
        
        return {
            'timestamp': ts, 'timestamp_sec': np.floor(ts * 10.0) / 10.0,
            'src2dst_packets': orig_p, 'dst2src_packets': resp_p,
            'src2dst_bytes': orig_b, 'dst2src_bytes': resp_b,
            'bidirectional_bytes': total_bytes,
            'bidirectional_duration_ms': dur,
            'bidirectional_mean_piat_ms': mean_piat,
            'bidirectional_stddev_piat_ms': std_piat,
            'bidirectional_mean_ps': mean_ps,
            'bidirectional_stddev_ps': std_ps
        }
    except Exception: return None

def parsear_linea_telemetria(linea):
    global OFFSET_GLOBAL
    partes = linea.lstrip('\ufeff').strip().split(',')
    if len(partes) < 9 or partes[0].strip().lower() == 'timestamp': return None
    try:
        ts_game = float(partes[0].strip())
        
        if OFFSET_GLOBAL == 0.0:
            OFFSET_GLOBAL = time.time() - ts_game
            print(f"[NIDS-AUTO-SYNC] Archivo sync no detectado. Auto-calibrando: {OFFSET_GLOBAL:.3f} s")
            
        ts_real = ts_game + OFFSET_GLOBAL
        
        return {
            'timestamp': ts_real, 
            'player_id': int(partes[1].strip()),
            'pitch': float(partes[5].strip()),
            'yaw': float(partes[6].strip()),
            'is_attacking': int(float(partes[7].strip())),
            'velocity': float(partes[8].strip())
        }
    except Exception: return None

# =====================================================================
# EVALUADOR PRINCIPAL (DATASET V3 EXACTO)
# =====================================================================
def bucle_evaluacion():
    ultimo_log = time.time()
    ultimo_estado = time.time()
    ultimo_log_modelo = 0.0
    ultimo_log_features = 0.0
    ultimo_heartbeat = 0.0
    clases_orden = ['Aimbot', 'Flood', 'LagSwitch', 'ninguno']

    if not os.path.exists(ALERTAS_LOG):
        with open(ALERTAS_LOG, 'w', encoding='utf-8') as f_alertas:
            f_alertas.write('timestamp,tipo_ataque,recuento\n')

    while True:
        time.sleep(INTERVALO_INFERENCIA_SEC)
        now = time.time()
        buffer_global.limpiar_obsoletos(now)
        df_red, df_tel = buffer_global.obtener_dataframes()

        if now - ultimo_heartbeat >= 10.0:
            print(
                f"[NIDS-LOOP] activo | red={len(df_red)} | "
                f"telemetria={len(df_tel)}"
            )
            ultimo_heartbeat = now

        if df_red.empty or df_tel.empty or len(df_tel) < 10: 
            if now - ultimo_log >= 10.0:
                est_red = "Vacío" if df_red.empty else f"OK ({len(df_red)} pkts)"
                est_tel = "Vacío" if df_tel.empty else f"OK ({len(df_tel)} frames)"
                motivo = ""
                if df_red.empty:
                    motivo = "falta red Zeek"
                elif df_tel.empty:
                    motivo = "falta telemetría"
                elif len(df_tel) < 10:
                    motivo = f"telemetría insuficiente ({len(df_tel)}/10 frames)"
                print(f"[NIDS-ESPERA] Red Zeek: {est_red} | Telemetría: {est_tel} | {motivo}")
                ultimo_log = now
            continue

        try:
            df_red_agg = df_red.groupby('timestamp_sec').agg({
                'src2dst_packets': ['sum', 'max'], 'dst2src_packets': ['sum', 'max'],
                'src2dst_bytes': ['sum', 'max'], 'dst2src_bytes': ['sum', 'max'],
                'bidirectional_bytes': ['sum', 'max'], 'bidirectional_duration_ms': 'mean',
                'bidirectional_mean_piat_ms': 'mean', 'bidirectional_stddev_piat_ms': 'mean',
                'bidirectional_mean_ps': 'mean', 'bidirectional_stddev_ps': 'mean'
            })
            df_red_agg.columns = ['_'.join(col).strip('_') if col[1] != '' else col[0] for col in df_red_agg.columns.values]
            df_red_agg = df_red_agg.rename(columns={
                'bidirectional_duration_ms_mean': 'bidirectional_duration_ms',
                'bidirectional_mean_piat_ms_mean': 'bidirectional_mean_piat_ms',
                'bidirectional_stddev_piat_ms_mean': 'bidirectional_stddev_piat_ms',
                'bidirectional_mean_ps_mean': 'bidirectional_mean_ps',
                'bidirectional_stddev_ps_mean': 'bidirectional_stddev_ps',
            }).reset_index()

            df_tel = df_tel.sort_values(['timestamp', 'player_id']).reset_index(drop=True)
            df_combinado = pd.merge_asof(
                df_tel,
                df_red_agg.sort_values('timestamp_sec'),
                left_on='timestamp', right_on='timestamp_sec',
                direction='backward', tolerance=0.5
            )

            # El entrenamiento rellena como máximo tres muestras por jugador.
            # Un ffill global mezcla los estados de los dos jugadores y cambia la
            # distribución de entrada del modelo.
            columnas_red = [col for col in df_red_agg.columns if col != 'timestamp_sec']
            df_combinado['red_match'] = df_combinado['timestamp_sec'].notna()
            ultimo_paquete = df_combinado['timestamp_sec'].where(
                df_combinado['red_match']
            )
            ultimo_paquete = (
                ultimo_paquete.groupby(df_combinado['player_id'], sort=False)
                .ffill()
            )
            df_combinado['tiempo_desde_ultimo_paquete'] = (
                df_combinado['timestamp'] - ultimo_paquete
            ).clip(lower=0).fillna(0)
            if columnas_red:
                df_combinado[columnas_red] = (
                    df_combinado.groupby('player_id', sort=False)[columnas_red]
                    .ffill(limit=3).fillna(0)
                )

            df_combinado = df_combinado.sort_values(
                ['player_id', 'timestamp']
            ).reset_index(drop=True)
            
            # Cinemática Dinámica
            jugador = df_combinado.groupby('player_id', sort=False)
            diff_yaw = jugador['yaw'].diff().fillna(0)
            diff_pitch = jugador['pitch'].diff().fillna(0)
            df_combinado['delta_yaw'] = ((diff_yaw + 180) % 360 - 180).abs()
            df_combinado['delta_pitch'] = ((diff_pitch + 180) % 360 - 180).abs()
            df_combinado['delta_yaw_en_disparo'] = df_combinado['delta_yaw'] * df_combinado['is_attacking']
            df_combinado['delta_pitch_en_disparo'] = df_combinado['delta_pitch'] * df_combinado['is_attacking']
            
            df_combinado['vel_angular_yaw'] = (df_combinado['delta_yaw'] / RESOLUCION_FRAME_SEC).astype('float32')
            df_combinado['vel_angular_pitch'] = (df_combinado['delta_pitch'] / RESOLUCION_FRAME_SEC).astype('float32')
            df_combinado['acc_angular_yaw'] = (jugador['vel_angular_yaw'].diff().fillna(0) / RESOLUCION_FRAME_SEC).astype('float32')
            df_combinado['acc_angular_pitch'] = (jugador['vel_angular_pitch'].diff().fillna(0) / RESOLUCION_FRAME_SEC).astype('float32')
            df_combinado['jerk_angular_yaw'] = (jugador['acc_angular_yaw'].diff().fillna(0) / RESOLUCION_FRAME_SEC).astype('float32')
            df_combinado['jerk_angular_pitch'] = (jugador['acc_angular_pitch'].diff().fillna(0) / RESOLUCION_FRAME_SEC).astype('float32')

            df_combinado['ratio_velocidad_bytes'] = (df_combinado['velocity'] / (df_combinado.get('bidirectional_bytes_sum', 0) + 1)).astype('float32')

            # --- TOTALES Y RATIOS DE RED ---
            p_src = 'src2dst_packets_sum'
            p_dst = 'dst2src_packets_sum'
            b_src = 'src2dst_bytes_sum'
            b_dst = 'dst2src_bytes_sum'
            
            df_combinado['packets_total'] = df_combinado.get(p_src, 0) + df_combinado.get(p_dst, 0)
            df_combinado['bytes_total'] = df_combinado.get(b_src, 0) + df_combinado.get(b_dst, 0)

            df_combinado['packets_per_second'] = (df_combinado['packets_total'] / RESOLUCION_FRAME_SEC).fillna(0).astype('float32')
            df_combinado['bytes_per_second'] = (df_combinado['bytes_total'] / RESOLUCION_FRAME_SEC).fillna(0).astype('float32')

            df_combinado['packets_total_diff'] = df_combinado['packets_total'].diff().fillna(0).astype('float32')
            df_combinado['bytes_total_diff'] = df_combinado['bytes_total'].diff().fillna(0).astype('float32')
            df_combinado['packets_acceleration'] = df_combinado['packets_total_diff'].diff().fillna(0).astype('float32')
            df_combinado['bytes_acceleration'] = df_combinado['bytes_total_diff'].diff().fillna(0).astype('float32')

            df_combinado['bytes_ratio'] = (df_combinado.get(b_src, 0) / (df_combinado.get(b_dst, 0) + 1)).astype('float32')
            df_combinado['packets_ratio'] = (df_combinado.get(p_src, 0) / (df_combinado.get(p_dst, 0) + 1)).astype('float32')
            df_combinado['angular_speed_total'] = np.sqrt(df_combinado['vel_angular_yaw']**2 + df_combinado['vel_angular_pitch']**2).astype('float32')
            df_combinado['angular_acc_total'] = np.sqrt(df_combinado['acc_angular_yaw']**2 + df_combinado['acc_angular_pitch']**2).astype('float32')

            # --- VARIACIONES Y PORCENTAJES ---
            cols_diff = [p_src, p_dst, b_src, b_dst, 'bidirectional_bytes_sum']
            for col in cols_diff:
                if col in df_combinado.columns:
                    df_combinado[f'{col}_diff'] = df_combinado[col].diff().fillna(0).astype('float32')
                    df_combinado[f'{col}_pct_change'] = df_combinado[col].pct_change().replace([np.inf, -np.inf], 0).fillna(0).clip(-10, 10).astype('float32')

            # --- VENTANAS MÚLTIPLES ---
            ventanas = [5, 10, 20, 50, 100]
            columnas_ventana = [
                'velocity', 'vel_angular_yaw', 'vel_angular_pitch', 'acc_angular_yaw', 'acc_angular_pitch',
                'src2dst_packets_sum', 'dst2src_packets_sum', 'src2dst_bytes_sum', 'dst2src_bytes_sum',
                'bidirectional_bytes_sum', 'bidirectional_mean_piat_ms', 'bidirectional_stddev_piat_ms'
            ]
            
            for col in columnas_ventana:
                if col in df_combinado.columns:
                    for w in ventanas:
                        serie_rolling = jugador[col].rolling(w, min_periods=1)
                        df_combinado[f'{col}_roll_mean_{w}'] = serie_rolling.mean().reset_index(level=0, drop=True).fillna(0).astype('float32')
                        df_combinado[f'{col}_roll_std_{w}'] = serie_rolling.std().reset_index(level=0, drop=True).fillna(0).astype('float32')
                        df_combinado[f'{col}_roll_max_{w}'] = serie_rolling.max().reset_index(level=0, drop=True).fillna(0).astype('float32')
                        df_combinado[f'{col}_roll_min_{w}'] = serie_rolling.min().reset_index(level=0, drop=True).fillna(0).astype('float32')

            for w in ventanas:
                df_combinado[f'red_match_roll_mean_{w}'] = (
                    jugador['red_match'].rolling(w, min_periods=1)
                    .mean().reset_index(level=0, drop=True).fillna(0).astype('float32')
                )

            # --- COEFICIENTE DE VARIACIÓN ---
            for w in [5, 10, 20, 50]:
                for col in [p_src, p_dst, 'bidirectional_bytes_sum']:
                    if col in df_combinado.columns:
                        mean_temp = jugador[col].rolling(w, min_periods=1).mean().reset_index(level=0, drop=True)
                        std_temp = jugador[col].rolling(w, min_periods=1).std().reset_index(level=0, drop=True).fillna(0)
                        df_combinado[f'{col}_cv_{w}'] = (std_temp / (mean_temp.abs() + 1e-6)).replace([np.inf, -np.inf], 0).fillna(0).astype('float32')

            for col in features_base:
                if col not in df_combinado.columns: df_combinado[col] = 0

            X_matriz = df_combinado[features_base]
            X_scaled = scaler.transform(X_matriz)

            if now - ultimo_log_features >= 5.0:
                print(
                    f"[NIDS-FEATURES] generadas | filas={len(X_matriz)} "
                    f"| features={X_matriz.shape[1]}"
                )
                ultimo_log_features = now
            
            if USA_IF_CONSEJERO:
                features_if = [f for f in IF_FEATURE_CANDIDATES if f in features_base]
                n_features_if = getattr(modelo_if, 'n_features_in_', len(features_if))
                if len(features_if) != n_features_if:
                    raise ValueError(
                        f"El modelo IF espera {n_features_if} features, "
                        f"pero el manifiesto permite {len(features_if)}: {features_if}"
                    )
                indices_if = [features_base.index(f) for f in features_if]
                pred_if = modelo_if.predict(X_scaled[:, indices_if])
                X_final = np.column_stack((X_scaled, pred_if))
            else:
                X_final = X_scaled

            log_modelo = now - ultimo_log_modelo >= 5.0
            if log_modelo:
                print(
                    f"[NIDS-MODELO] Inferencia iniciada | modelo={TIPO_MODELO} "
                    f"| lote={len(X_final)} | features={X_final.shape[1]}"
                )
                ultimo_log_modelo = now

            # Predicción dinámica (CNNs vs Tabulares)
            if TIPO_MODELO == 'CNN_2D':
                num_features = X_final.shape[1]
                D = math.ceil(math.sqrt(num_features))
                pad_size = (D * D) - num_features
                X_padded = np.pad(X_final, ((0, 0), (0, pad_size)), 'constant')
                X_inf = X_padded.reshape(-1, D, D, 1)
                probs = modelo_principal.predict(X_inf, verbose=0)
                pred_cl = np.array([clases_orden[i] for i in np.argmax(probs, axis=1)])
                
            elif TIPO_MODELO in ['ANN', 'CNN']:
                X_inf = X_final.reshape((X_final.shape[0], X_final.shape[1], 1)) if TIPO_MODELO == 'CNN' else X_final
                probs = modelo_principal.predict(X_inf, verbose=0)
                pred_cl = np.array([clases_orden[i] for i in np.argmax(probs, axis=1)])
            else:
                if hasattr(modelo_principal, 'predict_proba'):
                    probabilidades = modelo_principal.predict_proba(X_final)
                    clases_modelo = getattr(modelo_principal, 'classes_', np.arange(probabilidades.shape[1]))
                    pred_indices = np.argmax(probabilidades, axis=1)
                    pred_cl = np.array([
                        clases_orden[int(clases_modelo[indice])] for indice in pred_indices
                    ])
                    confianza = np.max(probabilidades, axis=1)
                    pred_cl = np.array([
                        clase if clase == 'ninguno' or confianza[indice] >= umbrales.get(clase, 0.0) else 'ninguno'
                        for indice, clase in enumerate(pred_cl)
                    ])
                else:
                    pred_cl = modelo_principal.predict(X_final, verbose=0)
                    pred_cl = np.array([
                        clases_orden[int(pred)] if isinstance(pred, (int, np.integer)) else str(pred)
                        for pred in pred_cl
                    ])

            df_combinado['pred_live'] = pred_cl
            df_combinado['tipo_ataque'] = pred_cl
            df_combinado['confianza_ataque'] = 1.0
            if now - ultimo_estado >= 5.0:
                conteo_pred = pd.Series(pred_cl).value_counts().to_dict()
                print(
                    f"[NIDS-INFERENCIA] OK | filas={len(df_combinado)} "
                    f"features={X_matriz.shape[1]} | predicciones={conteo_pred}"
                )
                ultimo_estado = now
                ultimo_log_modelo = now
            df_combinado.to_csv(STREAM_LOG, mode='a', header=not os.path.exists(STREAM_LOG), index=False)
            ultimo_log = now 

            predicciones_ataque = pred_cl[pred_cl != 'ninguno']
            if len(predicciones_ataque) > 0:
                modas_ataque = pd.Series(predicciones_ataque).mode()
                ataque_modal = str(modas_ataque.iloc[0])
                recuento = int(np.sum(predicciones_ataque == ataque_modal))
                print(f"[ALERTA NIDS] {time.strftime('%X')} | Trampa: {ataque_modal} | Ataques: {len(predicciones_ataque)}/{len(pred_cl)} | Clase dominante: {recuento}")
                with open(ALERTAS_LOG, "a", encoding='utf-8') as f_alertas:
                    f_alertas.write(f"{now},{ataque_modal},{recuento}\n")

        except Exception as e:
            print(f"[ERROR INFERENCIA] {e}")

# =====================================================================
# BLOQUE MAIN
# =====================================================================
if __name__ == "__main__":
    print("[NIDS-RUN] Iniciando hilos de recolección en Docker...")
    
    threading.Thread(target=rastreador_dinamico, args=(BASE_PATH_LOGS, obtener_ultimo_log_zeek, parsear_linea_zeek, buffer_global.agregar_red, "Zeek"), daemon=True).start()
    threading.Thread(target=rastreador_dinamico, args=(BASE_PATH_TELEMETRIA, obtener_ultima_telemetria, parsear_linea_telemetria, buffer_global.agregar_telemetria, "Telemetría", actualizar_offset_desde_archivo), daemon=True).start()
    
    bucle_evaluacion()