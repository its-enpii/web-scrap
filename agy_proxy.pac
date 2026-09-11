function FindProxyForURL(url, host) {
    host = host.toLowerCase();
    if (host === 'localhost' || host === '127.0.0.1' ||
        dnsDomainIs(host, '.enpiistudio.com') || host === 'enpiistudio.com') return 'DIRECT';
    return 'SOCKS5 127.0.0.1:1080';
}
