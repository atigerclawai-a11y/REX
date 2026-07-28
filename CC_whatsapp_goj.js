#!/usr/bin/env node
/**
 * GOJ WhatsApp Monitor — Baileys WebSocket
 * Zero browser, zero windows, zero Chrome ever.
 * Session: ~/.whatsapp_bridge/baileys_auth/
 */

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const path = require('path');
const fs = require('fs');
const http = require('http');

const AUTH = path.join(require('os').homedir(), '.whatsapp_bridge', 'baileys_auth');
const TARGETS = ['main', 'attendance', 'plus'];
const KW = ['not coming',"won't be",'sick','absent','cancel','not attending','day off','not today','changing'];

function isChange(t) {
    const l = (t||'').toLowerCase().trim();
    return l === '+' || l === '-' || KW.some(k => l.includes(k));
}

function send(m) {
    const b = JSON.stringify({source:'whatsapp',...m});
    const r = http.request('http://127.0.0.1:8080/api/imessage/intel',
        {method:'POST',headers:{'Content-Type':'application/json'},timeout:5000},
        res => {res.on('data',()=>{});res.on('end',()=>{});});
    r.on('error',()=>{});
    r.write(b);
    r.end();
}

const qrcode = require('qrcode-terminal');

async function start() {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH);
    let qrShown = false;
    const sock = makeWASocket({
        auth: state,
        browser: ['Gold Health Systems', 'Chrome', '1.0.0'],
        syncFullHistory: false,
        markOnlineOnConnect: false,
    });

    sock.ev.on('connection.update', async (u) => {
        if (u.qr && !qrShown) {
            qrShown = true;
            process.stdout.write('\n=== SCAN QR ===\n');
            qrcode.generate(u.qr, { small: true });
            process.stdout.write('\nWhatsApp → Linked Devices → Link a Device\n');
            process.stdout.write('QR_RAW:' + u.qr + '\n');  // Hermes: render as PNG for Kato
        }
        if (u.connection === 'open') {
            console.log('✓ Connected');
            try {
                for (const c of (sock.chats?.all()||[]).filter(x => x.id?.includes('@g.us'))) {
                    let name = c.id;
                    try { const m = await sock.groupMetadata(c.id); name = m.subject||c.id; } catch {}
                    const low = name.toLowerCase();
                    if (!TARGETS.some(t => low.includes(t))) continue;
                    for (const m of (await sock.loadMessages(c.id, 30))) {
                        if (!m.message || m.key.fromMe) continue;
                        const text = m.message.conversation || m.message.extendedTextMessage?.text || '';
                        if (!text) continue;
                        send({group:name,sender:m.pushName||'x',text,is_schedule_change:isChange(text),timestamp:new Date().toISOString()});
                    }
                }
            } catch(e) { console.log('Load:', e.message); }
        }
        if (u.connection === 'close') {
            const r = new Boom(u.lastDisconnect?.error)?.output?.statusCode;
            if (r === DisconnectReason.loggedOut) { console.log('✗ Logged out'); return; }
            console.log(`✗ (${r}) reconnecting...`);
            setTimeout(start, 5000);
        }
    });
    sock.ev.on('creds.update', saveCreds);
    
    async function getGroupName(jid) {
        try {
            const meta = await sock.groupMetadata(jid);
            return meta.subject || jid;
        } catch { return jid; }
    }
    
    const relevantIds = new Set();
    
    sock.ev.on('groups.upsert', async (groups) => {
        for (const g of groups) {
            const name = g.subject || '';
            const low = name.toLowerCase();
            if (TARGETS.some(t => low.includes(t))) {
                relevantIds.add(g.id);
            }
        }
    });
    
    sock.ev.on('messages.upsert', async ({messages}) => {
        for (const m of messages) {
            if (!m.message || m.key.fromMe) continue;
            const text = m.message.conversation || m.message.extendedTextMessage?.text || '';
            if (!text) continue;
            const jid = m.key.remoteJid;
            // Skip if not a group
            if (!jid?.includes('@g.us')) continue;
            // Try to resolve group name and filter
            const name = await getGroupName(jid);
            const low = name.toLowerCase();
            if (low.includes('trident') || low.includes('capital')) continue; // spam filter
            send({group:name,sender:m.pushName||'x',text,is_schedule_change:isChange(text),timestamp:new Date().toISOString()});
        }
    });
}

process.on('SIGINT', () => process.exit(0));
process.on('SIGTERM', () => process.exit(0));
start().catch(e => { console.error(e); process.exit(1); });
