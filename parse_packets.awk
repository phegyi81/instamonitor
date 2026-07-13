# parse_packets.awk
#
# Shared tcpdump output parser used by capture.sh and label.sh.
# Reads tcpdump -q output on stdin and prints one normalized record per
# IPv4 TCP/UDP packet to stdout. The caller decides where to redirect it.
#
# Output format (pipe separated, 7 fields):
#   epoch_ts|proto|src_ip|src_port|dst_ip|dst_port|length
#
# Example tcpdump -q lines handled:
#   IP 192.168.1.100.54321 > 157.240.1.1.443: tcp 1200
#   IP 192.168.1.100.54321 > 157.240.1.1.443: UDP, length 1200
#
# IPv6 lines (IP6 ...) and malformed lines are skipped.

{
    # Only IPv4 packets ("IP"); tcpdump prints "IP6" for IPv6.
    if ($1 != "IP") next

    # Expect "src > dst:" layout.
    if ($3 != ">") next

    # Our own capture timestamp (seconds since epoch).
    ts = systime()

    # Source token: a.b.c.d.port  -> 5 dot-separated parts.
    n = split($2, a, ".")
    if (n < 5) next
    sport = a[n]
    sip = a[1] "." a[2] "." a[3] "." a[4]

    # Destination token has a trailing ':' -> strip it first.
    d = $4
    sub(/:$/, "", d)
    m = split(d, b, ".")
    if (m < 5) next
    dport = b[m]
    dip = b[1] "." b[2] "." b[3] "." b[4]

    # Protocol: tcpdump -q prints "UDP" for UDP, "tcp" for TCP.
    proto = "tcp"
    if (index($0, "UDP") > 0 || index($0, " udp") > 0) proto = "udp"

    # Length: prefer the "length N" keyword (UDP), else the last numeric
    # field (TCP -q prints "tcp N").
    len = ""
    for (i = 1; i <= NF; i++) {
        if ($i == "length") {
            len = $(i + 1)
            break
        }
    }
    if (len == "") {
        if (match($NF, /^[0-9]+$/)) len = $NF
    }
    if (len == "") next

    # Ports must be numeric (guards against odd tokens).
    if (sport !~ /^[0-9]+$/ || dport !~ /^[0-9]+$/) next

    print ts "|" proto "|" sip "|" sport "|" dip "|" dport "|" len

    # Flush periodically so the tail-follower sees data promptly.
    if (NR % 10 == 0) fflush()
}
