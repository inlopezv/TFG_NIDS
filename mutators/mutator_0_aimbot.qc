#ifdef SVQC

REGISTER_MUTATOR(tfg_aimbot, true);

// Propiedad personalizada para saber si el jugador tiene el aimbot activo
.float tfg_is_anomalous; 

// 1. Interceptar el comando por consola para activar/desactivar y etiquetar
MUTATOR_HOOKFUNCTION(tfg_aimbot, SV_ParseClientCommand)
{
    entity player = M_ARGV(0, entity);
    string cmd_name = M_ARGV(1, string);

    if (cmd_name == "tfg_toggle")
    {
        player.tfg_is_anomalous = !player.tfg_is_anomalous;
        
        // Registrar START/STOP para tu dataset de Machine Learning
        float label_file = fopen("tfg_etiquetas.csv", FILE_APPEND);
        if (label_file >= 0) 
        {
            string estado = player.tfg_is_anomalous ? "START" : "STOP";
            // Usamos la misma variable 'time' que usaste en la telemetría
            fputs(label_file, sprintf("%f,%d,%s\n", time, player.playerid, estado));
            fclose(label_file);
        }
        
        sprint(player, sprintf("Aimbot TFG: %s en t=%f\n", (player.tfg_is_anomalous ? "ON" : "OFF"), time));
        return true; 
    }
    return false;
}

// 2. Lógica del Aimbot ejecutada en cada frame
MUTATOR_HOOKFUNCTION(tfg_aimbot, PlayerPreThink)
{
    entity p = M_ARGV(0, entity);

    // Solo actuamos si es un jugador vivo y tiene la anomalía activada
    if (IS_PLAYER(p) && !IS_DEAD(p) && p.tfg_is_anomalous)
    {
        entity closest_enemy = NULL;
        float closest_dist = 9999999;
        
        // Buscar al jugador enemigo más cercano
        IL_EACH(g_players, IS_PLAYER(it) && !IS_DEAD(it) && it != p,
        {
            // Si tu servidor usa equipos, descomenta esta línea para no apuntar a aliados:
            // if (it.team == p.team) continue;

            float dist = vlen(it.origin - p.origin);
            if (dist < closest_dist) 
            {
                closest_dist = dist;
                closest_enemy = it;
            }
        });

        // Si encontramos un objetivo, forzamos la cámara
        if (closest_enemy)
        {
            // Calculamos el origen de la vista del jugador actual
            vector my_eye = p.origin + p.view_ofs;
            
            // Apuntamos ligeramente por encima del centro del enemigo (hacia la cabeza/pecho)
            vector enemy_pos = closest_enemy.origin; 
            enemy_pos_z += 15; 

            // Matemáticas de vectores para obtener los ángulos de Euler
            vector dir = normalize(enemy_pos - my_eye);
            vector aim_angles = vectoangles(dir);

            // IMPORTANTE en QuakeC: El eje pitch (X) suele estar invertido al usar vectoangles
            aim_angles_x = -aim_angles_x; 

            // Sobrescribimos los ángulos del jugador
            p.v_angle = aim_angles;
            p.angles = aim_angles;
            
            // fixangle en true obliga al cliente a aceptar los ángulos dictados por el servidor
            p.fixangle = true; 
        }
    }
    
    return false;
}

#endif