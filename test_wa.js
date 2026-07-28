const { default: makeWASocket, useMultiFileAuthState } = require('@whiskeysockets/baileys');

(async () => {
    const { state, saveCreds } = await useMultiFileAuthState('/Users/mainsobhelper/.whatsapp_bridge/baileys_auth');
    console.log('Auth state:', state.creds.registered ? 'REGISTERED' : 'NOT REGISTERED');
    
    const sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        browser: ['Mac OS', 'Chrome', '10.0'],
    });
    
    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr, pairingCode } = update;
        console.log('Update:', JSON.stringify({connection, qr: !!qr, pairingCode}));
        
        if (connection === 'open') {
            console.log('SUCCESS - Connected!');
            saveCreds();
            process.exit(0);
        }
        if (connection === 'close') {
            const code = lastDisconnect?.error?.output?.statusCode;
            console.log('CLOSED - status code:', code);
            process.exit(code || 1);
        }
    });

    sock.ev.on('creds.update', saveCreds);

    setTimeout(() => { 
        console.log('TIMEOUT after 15s'); 
        process.exit(2); 
    }, 15000);
})();
