#ifdef SVQC

REGISTER_MUTATOR(telemetry_ids, true);

float telemetry_file = -1;
float debug_file = -1;

MUTATOR_HOOKFUNCTION(telemetry_ids, PlayerPreThink) {
    entity p = M_ARGV(0, entity);
    
    if (telemetry_file < 0) {
        string fecha_hora = strftime(true, "%Y%m%d_%H%M%S");
        string nombre_archivo = sprintf("dataset_telemetria_%s.csv", fecha_hora);
        telemetry_file = fopen(nombre_archivo, FILE_APPEND);
        
        if (telemetry_file >= 0) {
            print(sprintf("==== [SYNC_TELEMETRIA] Tiempo interno: %f ====\n", time));
            fputs(telemetry_file, "timestamp,player_id,origin_x,origin_y,origin_z,pitch,yaw,is_attacking,velocity\n");
        }
    }
    
    if (debug_file < 0) {
        debug_file = fopen("debug_telemetria.txt", FILE_APPEND);
    }

    if (IS_PLAYER(p) && !IS_DEAD(p) && IS_REAL_CLIENT(p)) {
        
        int dispara = 0;
        
        // Inicializar telemetria_ultimo_disparo si no ha sido inicializado
        // (comparar con un número muy negativo para detectar basura)
        if (p.telemetria_ultimo_disparo < -1000) {
            p.telemetria_ultimo_disparo = time - 1; // Inicializar a hace 1 segundo
        }
        
        // Verificar si el último disparo fue en este frame (diferencia de tiempo < 1 frame)
        // frametime típicamente es 0.01-0.03, así que usamos 0.05 como threshold seguro
        float tiempo_desde_disparo = time - p.telemetria_ultimo_disparo;
        if (tiempo_desde_disparo < 0.05 && tiempo_desde_disparo >= 0) {
            dispara = 1;
            if (debug_file >= 0) {
                fputs(debug_file, sprintf("DISPARO DETECTADO en t=%f, player=%d, tiempo_desde=%f, dispara=%d\n", time, p.playerid, tiempo_desde_disparo, dispara));
            }
        }

        string parte1 = sprintf("%f,%d,%f,%f,%f,", time, p.playerid, p.origin_x, p.origin_y, p.origin_z);
        string parte2 = sprintf("%f,%f,%d,%f\n", p.v_angle_x, p.v_angle_y, dispara, vlen(p.velocity));

        
        // DEBUG: Escribir el valor de dispara antes de guardar al CSV
        if (debug_file >= 0 && dispara == 1) {
            fputs(debug_file, sprintf("  -> CSV escrito con dispara=%d en t=%f\n", dispara, time));
        }

        if (telemetry_file >= 0) {
            fputs(telemetry_file, strcat(parte1, parte2));
        }
    }

    return false;
}

#endif