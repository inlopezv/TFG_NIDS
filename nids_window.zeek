@load base/protocols/conn

module NIDSWindow;

export {
    redef enum Log::ID += { LOG };

    type Info: record {
        ts: time &log;
        src2dst_packets: count &log;
        dst2src_packets: count &log;
        src2dst_bytes: count &log;
        dst2src_bytes: count &log;
        bidirectional_bytes: count &log;
        bidirectional_duration_ms: double &log;
        bidirectional_mean_piat_ms: double &log;
        bidirectional_stddev_piat_ms: double &log;
        bidirectional_mean_ps: double &log;
        bidirectional_stddev_ps: double &log;
    };

    type Accumulator: record {
        first_ts: time;
        last_ts: time;
        last_packet_ts: time &optional;
        src2dst_packets: count &default=0;
        dst2src_packets: count &default=0;
        src2dst_bytes: count &default=0;
        dst2src_bytes: count &default=0;
        piat_sum_ms: double &default=0.0;
        piat_square_sum_ms: double &default=0.0;
        piat_count: count &default=0;
    };
}

global windows: table[conn_id] of NIDSWindow::Accumulator;

function packet_bytes(p: pkt_hdr): count
    {
    if ( p?$tcp )
        return p$tcp$dl;
    if ( p?$udp )
        return p$udp$ulen > 8 ? p$udp$ulen - 8 : 0;
    if ( p?$ip )
        return p$ip$len;
    return 0;
    }

function write_window(id: conn_id, a: Accumulator)
    {
    local packets = a$src2dst_packets + a$dst2src_packets;
    local bytes = a$src2dst_bytes + a$dst2src_bytes;
    local mean_piat = a$piat_count > 0 ? a$piat_sum_ms / a$piat_count : 0.0;
    local variance = a$piat_count > 1
        ? (a$piat_square_sum_ms - a$piat_sum_ms * a$piat_sum_ms / a$piat_count) / (a$piat_count - 1)
        : 0.0;
    local mean_ps = packets > 0 ? bytes / packets : 0.0;
    local variance_nonnegative = variance > 0.0 ? variance : 0.0;
    local stddev_piat = sqrt(variance_nonnegative);

    Log::write(LOG, [$ts=a$first_ts,
                     $src2dst_packets=a$src2dst_packets,
                     $dst2src_packets=a$dst2src_packets,
                     $src2dst_bytes=a$src2dst_bytes,
                     $dst2src_bytes=a$dst2src_bytes,
                     $bidirectional_bytes=bytes,
                     $bidirectional_duration_ms=(a$last_ts - a$first_ts) / 1msec,
                     $bidirectional_mean_piat_ms=mean_piat,
                     $bidirectional_stddev_piat_ms=stddev_piat,
                     $bidirectional_mean_ps=mean_ps,
                     $bidirectional_stddev_ps=0.0]);
    }

event new_packet(c: connection, p: pkt_hdr)
    {
    local id = c$id;
    local now = network_time();
    local bytes = packet_bytes(p);
    local is_orig = T;

    if ( p?$ip )
        is_orig = p$ip$src == id$orig_h;
    else if ( p?$ip6 )
        is_orig = p$ip6$src == id$orig_h;

    if ( id !in windows )
        windows[id] = [$first_ts=now, $last_ts=now];

    local a = windows[id];
    a$last_ts = now;

    if ( is_orig )
        {
        ++a$src2dst_packets;
        a$src2dst_bytes += bytes;
        }
    else
        {
        ++a$dst2src_packets;
        a$dst2src_bytes += bytes;
        }

    if ( a?$last_packet_ts )
        {
        local piat_ms = (now - a$last_packet_ts) / 1msec;
        a$piat_sum_ms += piat_ms;
        a$piat_square_sum_ms += piat_ms * piat_ms;
        ++a$piat_count;
        }

    a$last_packet_ts = now;
    windows[id] = a;
    }

event flush_windows()
    {
    for ( id in windows )
        write_window(id, windows[id]);
    windows = table();
    schedule 1sec { flush_windows() };
    }

event zeek_init()
    {
    Log::create_stream(LOG, [$columns=Info, $path="nids_conn"]);
    print "[NIDS-ZEEK] Agregador de ventanas de 1 segundo cargado";
    schedule 1sec { flush_windows() };
    }