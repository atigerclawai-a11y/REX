#!/usr/bin/env node
/**
 * CC_whatsapp_ws.js — WhatsApp WebSocket Bridge v4
 * =================================================
 * Uses Baileys 7.x pairing code (NO QR CODE NEEDED).
 * Phone number is hardcoded. When run, generates a code
 * the user types into WhatsApp → Linked Devices → Link with phone number.
 */

const path = require('path');
const fs = require('fs');
const http = require('http');
const crypto = require('crypto');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, makeCacheableSignalKeyStore } = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');

const STATE_DIR = path.join(require('os').homedir(), '.whatsapp_bridge');
const AUTH_DIR = path.join(STATE_DIR, 'baileys_auth');
const POLL_INTERVAL = 60;
const PHONE_NUMBER = '13475879913'; // Kato's number

let sock = null;
let isConnected = false;
let messageQueue = [];

function makeMsgId(text, sender, ts) {
    return crypto.createHash('md5').update(`${text}|${sender}|${ts}`).digest('hex').slice(0, 12);
}

function isScheduleChange(text) {
    if (!text) return false;
    const low = text.toLowerCase().trim();
    if (low === '+' || low === '-') return true;
    return ['not coming', "won't be", 'wont be', 'not in', 'staying home', 'sick', 'no today', 'not today', 'changing', 'change day', 'absent', 'cancel', "won't make", 'wont make', "can't come", 'cant come', 'not attending', 'day off', "won't attend"].some(kw => low.includes(kw));
}

function postDataRex(payload) {
    return new Promise((resolve) => {
        const data = JSON.stringify({ source: 'whatsapp', ...payload });
        const req = http.request('http://127.0.0.1:8080/api/imessage/intel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) },
            timeout: 5000,
        }, (res) => { res.on('data', () => {}); res.on('end', () => resolve(true)); });
        req.on('error', () => resolve(false));
        req.write(data);
        req.end();
    });
}

async function processQueue() {
    if (messageQueue.length === 0) return;
    const batch = messageQueue.splice(0);
    console.log(`[ws] ${batch.length} messages sent`);
    for (const m of batch) await postDataRex(m);
}

async function main() {
    console.log('[ws] WhatsApp Bridge v4 (pairing code mode)');
    
    // Remove stale auth so we get a fresh pairing
    if (fs.existsSync(AUTH_DIR)) {
        fs.rmSync(AUTH_DIR, { recursive: true });
        console.log('[ws] Cleared stale auth for fresh pairing');
    }
    
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    
    sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        browser: ['Gold Health Systems', 'Chrome', '1.0.0'],
        syncFullHistory: false,
        markOnlineOnConnect: false,
        // Don't generate QR - use pairing code instead
        generateHighQualityLink: false,
    });

    sock.ev.on('connection.update', async (update) => {
        const { connection, lastDisconnect, qr } = update;
        
        if (qr) {
            // Instead of showing QR, request a pairing code
            try {
                const pairingCode = await sock.requestPairingCode(PHONE_NUMBER);
                console.log('\n═══════════════════════════════════════════');
                console.log('  LINK YOUR PHONE — NO QR CODE NEEDED');
                console.log('═══════════════════════════════════════════');
                console.log('');
                console.log('  On your phone:');
                console.log('  1. Open WhatsApp');
                console.log('  2. Go to Settings → Linked Devices');
                console.log('  3. Tap "Link a Device"');
                console.log('  4. When it asks to scan QR, tap');
                console.log('     "Link with phone number instead"');
                console.log('  5. Enter this code:');
                console.log('');
                console.log(`       🟢  ${pairingCode}  🟢`);
                console.log('');
                console.log('═══════════════════════════════════════════\n');
            } catch (e) {
                console.log('[ws] Pairing code error:', e.message);
            }
        }
        
        if (connection === 'open') {
            isConnected = true;
            console.log('[ws] ✅ CONNECTED!');
            // Start polling
            pollGroups();
        }
        
        if (connection === 'close') {
            isConnected = false;
            const reason = new Boom(lastDisconnect?.error)?.output?.statusCode;
            console.log(`[ws] Disconnected (${reason}). Reconnecting...`);
            if (reason !== DisconnectReason.loggedOut) {
                setTimeout(main, 5000);
            }
        }
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('messages.upsert', async ({ messages }) => {
        for (const msg of messages) {
            if (!msg.message || msg.key.fromMe) continue;
            const text = msg.message.conversation || msg.message.extendedTextMessage?.text || '';
            if (!text) continue;
            messageQueue.push({
                group: msg.key.remoteJid,
                sender: msg.pushName || msg.key.participant?.split('@')[0] || 'unknown',
                text,
                source: 'whatsapp',
                is_schedule_change: isScheduleChange(text),
                timestamp: msg.messageTimestamp ? new Date(msg.messageTimestamp * 1000).toISOString() : new Date().toISOString(),
            });
        }
    });

    async function pollGroups() {
        if (!isConnected || !sock) return;
        try {
            const chats = sock.chats?.all() || [];
            for (const c of chats.filter(c => c.id?.includes('@g.us'))) {
                let name = c.id;
                try {
                    const meta = await sock.groupMetadata(c.id);
                    name = meta.subject || c.id;
                } catch {}
                const low = name.toLowerCase();
                if (!['main', 'attendance', 'plus'].some(t => low.includes(t))) continue;
                
                const msgs = await sock.loadMessages(c.id, 30);
                for (const msg of msgs) {
                    if (!msg.message || msg.key.fromMe) continue;
                    const text = msg.message.conversation || msg.message.extendedTextMessage?.text || '';
                    if (!text) continue;
                    messageQueue.push({
                        group: name,
                        sender: msg.pushName || msg.key.participant?.split('@')[0] || 'unknown',
                        text,
                        source: 'whatsapp',
                        is_schedule_change: isScheduleChange(text),
                        timestamp: msg.messageTimestamp ? new Date(msg.messageTimestamp * 1000).toISOString() : new Date().toISOString(),
                    });
                }
            }
            await processQueue();
        } catch (e) {
            console.log(`[ws] Poll error: ${e.message}`);
        }
    }

    // Poll every 60s
    setInterval(async () => { if (isConnected) await pollGroups(); }, POLL_INTERVAL * 1000);
}

process.on('SIGINT', () => { if (sock) sock.end(); process.exit(0); });
process.on('SIGTERM', () => { if (sock) sock.end(); process.exit(0); });

main().catch(e => { console.error('[ws] Fatal:', e); process.exit(1); });
