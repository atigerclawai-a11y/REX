#!/usr/bin/env node
/**
 * GOJ WhatsApp Monitor — Baileys WebSocket v2
 * =============================================
 * Zero browser, zero windows, zero Chrome ever.
 * Session: ~/.whatsapp_bridge/baileys_auth/
 *
 * v2 CHANGES (2026-07-31):
 *   - Death spiral detection: 3+ Connection Failures in 60s → auto pairing code
 *   - Pairing code fallback: when QR would be shown, requests 8-char code instead
 *   - Cleans up: proper exit on loggedOut + max retries cap
 */

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const path = require('path');
const fs = require('fs');
const http = require('http');

const AUTH = path.join(require('os').homedir(), '.whatsapp_bridge', 'baileys_auth');
const PHONE = '13475879913';
const TARGETS = ['main', 'attendance', 'plus'];
const KW = ['not coming',"won't be",'sick','absent','cancel','not attending','day off','not today','changing'];
const DEATH_SPIRAL_THRESHOLD = 3;     // failures
const DEATH_SPIRAL_WINDOW = 60_000;   // ms
const MAX_RETRIES = 20;               // hard cap before exit

let failureTimestamps = [];
let retryCount = 0;

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

function isDeathSpiral() {
    const now = Date.now();
    failureTimestamps = failureTimestamps.filter(t => now - t < DEATH_SPIRAL_WINDOW);
    return failureTimestamps.length >= DEATH_SPIRAL_THRESHOLD;
}

async function start() {
    const { state, saveCreds } = await useMultiFileAuthState(AUTH);
    let codeShown = false;

    const sock = makeWASocket({
        auth: state,
        browser: ['Gold Health Systems', 'Chrome', '1.0.0'],
        syncFullHistory: false,
        markOnlineOnConnect: false,
    });

    sock.ev.on('connection.update', async (u) => {
        // ── QR received → request pairing code instead ──
        if (u.qr && !codeShown) {
            codeShown = true;
            try {
                const pairingCode = await sock.requestPairingCode(PHONE);
                console.log('\n═══════════════════════════════════════════');
                console.log('  RE-PAIRING REQUIRED');
                console.log('═══════════════════════════════════════════');
                console.log('  Code:', pairingCode);
                console.log('  Phone: Settings → Linked Devices → "Link with phone number"');
                console.log('═══════════════════════════════════════════\n');
                console.log('PAIRING_CODE:' + pairingCode);
            } catch (e) {
                // Fallback to QR if pairing code fails
                const qrcode = require('qrcode-terminal');
                console.log('\n=== SCAN QR (pairing code failed: ' + e.message + ') ===');
                qrcode.generate(u.qr, { small: true });
                console.log('QR_RAW:' + u.qr);
            }
        }

        // ── Connected! ──
        if (u.connection === 'open') {
            console.log('✓ Connected to WhatsApp');
            failureTimestamps = [];
            retryCount = 0;
            
            // Load initial group history
            try {
                const chats = sock.chats?.all() || [];
                for (const c of chats.filter(x => x.id?.includes('@g.us'))) {
                    let name = c.id;
                    try { const m = await sock.groupMetadata(c.id); name = m.subject||c.id; } catch {}
                    const low = name.toLowerCase();
                    if (!TARGETS.some(t => low.includes(t))) continue;
                    const msgs = await sock.loadMessages(c.id, 30);
                    for (const m of msgs) {
                        if (!m.message || m.key.fromMe) continue;
                        const text = m.message.conversation || m.message.extendedTextMessage?.text || '';
                        if (!text) continue;
                        send({group:name,sender:m.pushName||'x',text,is_schedule_change:isChange(text),timestamp:new Date().toISOString()});
                    }
                }
                console.log('✓ Initial history loaded');
            } catch(e) { console.log('Load history:', e.message); }
        }

        // ── Disconnected ──
        if (u.connection === 'close') {
            const r = new Boom(u.lastDisconnect?.error)?.output?.statusCode;

            if (r === DisconnectReason.loggedOut) {
                console.log('✗ Logged out — auth rejected. Will need fresh pairing.');
                process.exit(1);
            }

            // Track failures for death spiral detection
            failureTimestamps.push(Date.now());
            retryCount++;

            if (retryCount > MAX_RETRIES) {
                console.log(`✗ Max retries (${MAX_RETRIES}) reached. Exiting. Launchd will restart.`);
                process.exit(1);
            }

            // Death spiral → reset codeShown so next attempt requests pairing code
            if (isDeathSpiral()) {
                console.log(`⚠ Death spiral detected (${failureTimestamps.length} failures in ${DEATH_SPIRAL_WINDOW/1000}s). Will request pairing code on next attempt.`);
                codeShown = false;
                // Wait longer before retry in death spiral
                console.log(`✗ (${r}) Waiting 30s before retry...`);
                setTimeout(start, 30_000);
                return;
            }

            console.log(`✗ (${r}) Retry ${retryCount}/${MAX_RETRIES} — reconnecting in 5s...`);
            setTimeout(start, 5_000);
        }
    });

    sock.ev.on('creds.update', saveCreds);

    // ── Group name resolver ──
    async function getGroupName(jid) {
        try {
            const meta = await sock.groupMetadata(jid);
            return meta.subject || jid;
        } catch { return jid; }
    }

    // ── Group discovery ──
    sock.ev.on('groups.upsert', async (groups) => {
        for (const g of groups) {
            const low = (g.subject || '').toLowerCase();
            if (TARGETS.some(t => low.includes(t))) {
                console.log(`  Group found: ${g.subject}`);
            }
        }
    });

    // ── Live messages ──
    sock.ev.on('messages.upsert', async ({messages}) => {
        for (const m of messages) {
            if (!m.message || m.key.fromMe) continue;
            const text = m.message.conversation || m.message.extendedTextMessage?.text || '';
            if (!text) continue;
            const jid = m.key.remoteJid;
            if (!jid?.includes('@g.us')) continue;
            const name = await getGroupName(jid);
            const low = name.toLowerCase();
            if (low.includes('trident') || low.includes('capital')) continue;
            send({group:name,sender:m.pushName||'x',text,is_schedule_change:isChange(text),timestamp:new Date().toISOString()});
        }
    });
}

process.on('SIGINT', () => process.exit(0));
process.on('SIGTERM', () => process.exit(0));

// Brief delay for launchd throttle before starting
setTimeout(() => {
    start().catch(e => { console.error('Fatal:', e.message); process.exit(1); });
}, 2000);
