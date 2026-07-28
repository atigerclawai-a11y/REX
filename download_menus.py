#!/usr/bin/env python3
"""Download menu scan PDFs from Gmail for April 27 – May 1, 2026."""
import json, os, base64, urllib.request, urllib.parse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "gmail_token.json")
OUT_DIR    = os.path.join(SCRIPT_DIR, "signins")

ATTACHMENTS = [
    ("19dcf988af0eeef5", "ANGjdJ_YJ6u2yaQAiDrJL7dN0WtgwrRUR3Ge5DAOGiO9rhzt1kDRRvg8ekvCvy34_D1qfAOXSRoGEqOiMHXcBZ_L8UWlhtwZBP6Ix0ceMVh2Sq877rtsFY4uB2Ua8JUiUgVcLcioq1Rcph1pxq4olZIrmhwOorKoXNHGMibIQR49a9w43UJjQIiEgd2nVaIwr-mzNDRJglRiBMTbzClEiasTWuttUeEeMDKqfQdSIfuslSkgpWJbdO-rYQF2AbB0ZCqKvqXOVptZVVbhvajkAzmjRyt8pu15i9o-RYRo5bjaAWXWV2gN2CTefLZUO4m6G0sO_QogKfD5WIR2aLNanmSIuQfBBS1jy4kBsiQPK0VJnehFkkQeu_nMwQznwXAhwsEd9pld2U3kMvmwvRi7WEyPM1-pFrkvB7vhOfyS3Q", "scan_20260427_1124"),
    ("19dd9b09a0afbba1", "ANGjdJ_mb7Vj95O7ofCFRHcR-1_Nv2kbPj4c1e68pxqOHd8J1gD55uV4_NnbSxeK_itwKHYU6jY0zVAKYVYOCQTAF6Z1bIc2KjXGxkqkcX5zpy5NiQU37NCt2UorRo5MlIy9pINN0QHaS9YfCpi5Bv6pyIgUqxSqDyFrs-PtDGYRWNrvRhk6FmOlwIlSYl2Dei_rSH6DVNn8BIfG8vb4L9nrKY5fcB8vp4LFgJsuSsMpuqPAusfLgyMD4Jo-Uku6aBQEh6mbzDpcIa5maPXblR9Gl7d23wIcXGxmgZcg0aqx1sMeQZ_Qu85TwiSQV8LeBMc_rBcXKYPCdQ5HglcxPQiV9-L6D-Ira7QRm4x08eykPimiJjSWxyrx6AvJSx8aXmIfcmSp0jGxOCqoaPXknccjEJZF50OfEKaYVt58kg", "scan_20260427_1525a"),
    ("19dd9ae224543f52", "ANGjdJ8oWssKSZKYw-VYq4CdVCr5Cw9dh9vGUQacjo9fDBHfOziMp9MstaRlhc9xWTtVSPJmmd3x_yFJsqvwDqzGnlyULBb6k3ft1mgH36QIWLRW_ZpGbpFrAAnFZH4FAojW4PGVGw5V9mwgTPx065R0ZV75RIeUUp4GkXAIukS733RBqgYDF8NviW_cIwVSYyKDrI54qtTbFyswODtRmyNmdkuHpvYrRiYdlwIJ9-ewBqZUE6pA7LUHkPRTdZC6F65oTUnVBoDPRglPSIpecB49W1VYNVWCf5h4PgUA9_PnDmSpW_qYY9X6r51zZCN4DjHdqIjzt_j3TI5_n_GMbFx6_D1dvt77fr7XgXqIqweS2fltB_J4THD8qvJA4i7KfD87s0Byw5jGr0bDLGV6Rx0XJKBkqQ_v2zcV0qPuVg", "scan_20260427_1525b"),
    ("19dd9ad97cc93938", "ANGjdJ8JxTGM9ePBvD-EhXh3wIfxfon92fiJiO1oJUUzg-QreYHgLkK7rBqVJlCRPBgQ2ExJCizAVhKxOyhGFOHA9d1VRsnRGtWiHL2RyHWtgesgvTZNmGUjC-CI77OKgYtJnMmI99EwsEfzKvWX_S7LKHAsiQUuq5b2g1kmHkoG_6-OVU3s0I1WrafqMwdWjq_GLv0AnEuWcVO_JexbJ-fbsAzpgKOdFJFoXzAs8k8hESBvIerGfPDcLGPPhivrONhGQpzPSigj-7rIynDGkhb6lenkvh-88vt_rzuYc4zrH5f0EQv1UDt_RLonRY4BIHA_0CyVfVcBw7ggdDz1R1azyf6S3q_H0KadMlIc4xRpMnrMxH8QQhIMAgtjYrCfU4srfODK1jpfSTc39PQCxx0htYXSExHTIiii3Bfpqw", "scan_20260427_1526"),
    ("19dd9aa864c953a6", "ANGjdJ8ci-6S6TY9tkDf6R-2Grr1KOvyD6qdvOzT2Vv_PrK192nofjErgIXInIDdh_7kAYOkFZytxOZx10lCxayDLTqwvhVeQkS92MVhcLnEAvvpC0Dov21e_0CQtT0gTTIV7NPoCR5qe9PicjJzLBRkC8wMlXpCeV-ykarUqRVLXLf24ewMHESCjuEwELa16_BOSfRkywb5BbNcT1viXvC9BUwXoci60Kn6fqm1h1crNYBxv-tsZ-sTvMMYWhXdan6QcvykPDFmpStps--Nro2cJocevMgzq9JAepAcATVabktChtB-mRuDqnVR0haOfvWoJxvPfgRjaxj_jKnt6yKqUYBAM4CAjn0fHJyf7HfZgbS91qJbi6n1vQDXJHoreW5FLYBPd-xoJ6kdxKN09BHxRMUx0hlcoMCWCyl0LQ", "scan_20260427_1527"),
    ("19dd9a99e0e1fffe", "ANGjdJ-mpz_5ZOF6ZZ2HDSwy5R9CWzbT-qgRgpzuzDlOzlbcSwYROhfMhyAHEynW3skOlLeUqMUlcNwGpv_U1oJfTTxMTkmiDk-I-EJUhzFiTq_umqmRNNW9epP7lAeuMC9IHI8nRgH0pCrLJ5w4TDZVXtzZn6w5n__xR1QQaKRApkNtBx29afKtShfgu80vEjZKJyVpfPaZWdbJb5QpOv2MWFGwqym0Pfm1kHu0itYHN-f4CL9XA3hhCTycnGqR7Xbvque8Il7aV8a2qB3ziBuC_752LyJorQ9wjLo-zYkEavTLKHp4FnKRrZ7uX9D5Pe4ZkS06uQfw9S12bikdFxiyRaB8eUT-ppa1hQXmWwQK8wzhHQ3z0CMcmwFG4lRIuJDjOq7kI0jNd9grRyFeavucOX_Ne_2NeShJcI3lGQ", "scan_20260428_0443"),
    ("19dd9a920525fb3c", "ANGjdJ9N6ufadPKIU1CE05L0Rx6anM1aHz_wWU9VeJRuJsV1NHnfd89AQKugcM34apLqGpsCDwgzK7bcvGhbieW8EpNIEf-hlWtO4lf7NWmIGgGlqva1WixMi1PMnsKnbdf22ubOBbd9jQhpCnlBlHBLQXEzuKreYz30wm_Vcmy9PjKLuQ3hpJEgAq0HgxohijfWR_WzlZvVBojAxDG4KCH0QzzYUOt1bHe3LvJVPzDABMAuAEYKBDqonReKbPy4DElvHa7IJh1EPE6EU4qyulVctJtCjFUwx5cYePcafeCB-QSF6X2TPX3irVq1dMy0F3SDRCEvEl4UCK4p6kzsE1fCwXt-YchFhyLAn7TGZoguD9rfJRxxhAP7H6OGNrEhpjESU6g37QOH-kb_dPEiv_H1skkjhcC_QO1XdTkHHg", "scan_20260428_1211"),
    ("19dd9a787fb25393", "ANGjdJ_zvhI49AsgJTjJoWJacSdR8u_DYMriBvjk04Xi02s-ni86eMxNqI0quwQ4GlUrNwQEZuf6VyJfaOfLDvXMYLJ8_69IPkgpb8-8weDMp9eQGRkvSRSZFLXesgWG3xtL1edcKa810omzgwUN3zQSpyPZAy-Gj_KWvVlN59-59v5uC9gTMkfyS7JTaEtVPKqWf07n3IBvT1Yf-zOkCLVjyVqHTdHIiTsUoPyna6NkDh30IsqVpJbKDqZ1j1cqSx_SzZd5k7hUz6MllJk4n3V7bZIVOsZjElNdeLIcH0ZX93Q4wJcby4RtS6L831-y-FVyDeqGFlId1AfunWYyTCRUba7mjcgo9fpcJUWkoPjk5FRA5RVXrl9r_79JCYWpEwKvCXUfxe3bSG-cqwehqsFxb7yVKs1kverX9_2q4w", "scan_20260429_0442"),
    ("19dd9a745329cc6d", "ANGjdJ-EdqOL3zZOohogjNVxjk26Qu_jfzFm8j4Iu8okPslPC0H9LylwS0M04VWfeJVNEYyC9e3iNjByvTd9MilXsVLxtsRqCABfl6N2geRaH89dQNQtovlFB2kN2j56jinNUVYnhDktmNDuB9xnKCuaeOj97noTDyzF592ZTNqo5YRa5qyWhVJhAfYDBm4O81iDV8TbWJfk-ma3dwGLj5o7mKJ0beFtgM_lM1x-ZnOdxODm8f4fmRnEtCp2_34MjMb-A_dl9Lk13K5UCiqdRb_CEgwfLIDb79k1LnDsViRm2nV3F9g_E4E-eL3VySM7b1WSzWLOSZHwpZ2_NaMETIS4VgZ-2YAfkdaIK9tOf55uQNxlVYR06N1-mZRTSkWkwJep5lkuNeyQ-udKvMnvazZBz4K1J4mvl-gc_cxY8Q", "scan_20260429_0443"),
    ("19de58519017f206", "ANGjdJ-95YeUDfQxrrU__2o31GaGn-4HBvxPdKHxBAYRrEo5KcM2cN9bC-fTzGlX9RPTsB09rrRt2obDExxhE25WNiI0OQMqUYkv-C2U-BftZIV-iuKB43sV3IVF1aV-kql4nK-EcfU7cyoUYqD6eD08x6dhvtn-xAN9ZC4p8lw0-BIUNOAHQED8tqUply_MBUf3p3RaZaxx0jIZ8cYRrkZnqXA1XNj-w_Gjwm_CX-RjJGboLGvaajuBLsaX4T28d7YXqeH50-rafZfq_1sXLw0d32enF-JMiOcEp5LiIlDkwiCbO6iz7qf4tRn6dQHMCbxyFHC_m9cA7S4YFCTpgCC_RKR55neD63eH-LCm0Cc6eZA4fucr7q-jhANM5VhpjMMqsKRUTIW2hFMncUIqVPdYKsFApTXIyMo2OysgjA", "scan_20260501_1217"),
    ("19de586f9ee5d7aa", "ANGjdJ9LkHJLjU8oqV-o2Pa1Vec0JFI3uA9C2YhncCCxbp9sVwE2ZNGp05ECDroQYu_RsX5athZADDsA8F2xbzYMDZXBYnCNpM9qB13Dl1RyBjZHf9jeuE6eAIM247J5snmRDt710_doY-rxw-eZZaAxFmDJnZn7h4brhiTC8dlk-tRg6wMzrRUl0DLN6BJe967Cr3WmyyEqRjUf3L3oQ9FqQhgC6X1ApjDeO6P8lcAkHf64QbqGgM6w-mpcm9M8Ym2FboIgMc7fHi7L6_cNRlEu_jTLNWmrJgyzE-Jx10K68tpvbrDNFXPWLt5vX-sqMxG4ZpVBbQmmpd80ZSCanO7S6dNaRBbdZnBTS_K7QzahpCEktIqDAB_XUUqDY6FI7X7VQuU_HaL1PqdFlWAAuDgkixnYJ3N1Sy2P1z9V4Q", "scan_20260501_1514"),
    # New batch forwarded May 2 — menus from Apr 29–30
    ("19de6671e6a1f4a5", "ANGjdJ-S-Ee3lWXa4lkxS-dgBml2WIF3T0dkJK0LWAp9oy7SMCGjutNX8Da6N-QBrSNxT_JGahMceBVo157_5ZmKE9cdNsbUHI5qAg1Hq1oKeYvfw5fYG7d7-pwUk9KcZW6SqQVBz5Zvapb9vM7BUfPqa1W_agndOx0Y4D9WOXcx3jxgfreG2dcgASf8EtikakTAN2zmQYbUDTV1sJAC7xieXgP87OkwUyZO7NYiqZSlJ_oD1t3by4P931dFeYODookFS5NKrZ0RoDSs84U8U1pLnPIkGVjrpiD8d8w4vgjKwAqYBe8ojI6WFBV129fWGWurkZWsa5mOl3x01ds1ZovrHFBFsDMvRoRnVqsD1YaAy0vZVMyZ6Y__tpzYR7wlTcRT37_M7LlE6ShZqZD36lyEFkJDmH2JyRIPeuI9DA", "scan_20260429_1051"),
    ("19de663d6150d19c", "ANGjdJ8Fulr898LPwPJd7PT7kmqjqkxTRF5G9JXwvLiwasmpHiK2qCHS5c2huEF6qRyDi-HLWKVWqmC_h4SZvEWesic0YPso_UZtTh1Rf3ck97MIJN75fzJIlzEtTF38kiQPSXq9B1Go9xjGu-Zem9U20HKmjAe01zDPIe0eF3Eybs2tdNtTAowUWvoHuyvIf5KFYX0CF9B2N4hRU4hYQXwFuBBktOCE-XPAzDSZW-mSVzZ9uDZ2eUBzpSfAmsKCVxx9SoBslqfB1-Gvjjek9-ZYJIqb9P8bDapFq_zQH2IG94ASPjcpha-PQHfpzYzSA-VG0E4kT07VrbYqK9iEvm3Ic4Rf-ytxmMmoF8WTiRUhk7XuplEs3tPcovjr2qFURKDUuJBZHpCBieQZk4K5OP7EJP_lN2xMZmQKYLKR4A", "scan_20260430_1041"),
    ("19de669e98ec3af6", "ANGjdJ_Y6HYNov-ZxSv5Gp66FhQdDQoXgPjMAOu5liRmG2AhQFpSqpR25dKhemYF7u7GDJywpLe9O4kQYks5Yb23AaiTMhSYdztGc98moewSIH_eVG7CyfUDHAuPiAKclb9WY954TtxODGQ5YyzG2ioFDHgl-lfShzMaHrjJ8A7qOBGgOr2gXFbzJdiqU-hfELMATjFw8BDmegR2KySOqickaBvbdx23Z6PitHfFkDH0r2eZdZSdm8RBIEZ1zmq7-D7z7GPxiCx3Bsf_d3Hcv9_vP8oJ6b7gg4pH5UAn_VxotjBhhsXOv-pF5Za4je60gJ9tHJkmmGXu15eqmtuuMvFNVfW1ELa6O8ldKXpSBVVUQ__oGG-c2g4h-OP5PKOcd-dlytPldlkgdBoC7tyNd4JgHT8ZhHpnOOPtEvKyCw", "scan_20260430_1516"),
]

def refresh_token(tok):
    data = urllib.parse.urlencode({
        "client_id":     tok["client_id"],
        "client_secret": tok["client_secret"],
        "refresh_token": tok["refresh_token"],
        "grant_type":    "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]

def main():
    with open(TOKEN_FILE) as f:
        tok = json.load(f)
    access_token = tok["token"]

    os.makedirs(OUT_DIR, exist_ok=True)

    for msg_id, att_id, label in ATTACHMENTS:
        out_path = os.path.join(OUT_DIR, f"{label}.pdf")
        if os.path.exists(out_path):
            print(f"  skip (exists): {label}.pdf")
            continue

        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}/attachments/{att_id}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
        try:
            with urllib.request.urlopen(req) as r:
                body = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print("  token expired, refreshing...")
                access_token = refresh_token(tok)
                req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
                with urllib.request.urlopen(req) as r:
                    body = json.loads(r.read())
            else:
                print(f"  ERROR {e.code} on {label}: {e.reason}")
                continue

        pdf_bytes = base64.urlsafe_b64decode(body["data"] + "==")
        with open(out_path, "wb") as f:
            f.write(pdf_bytes)
        print(f"  saved: {label}.pdf  ({len(pdf_bytes):,} bytes)")

    print("\nDone. PDFs saved to:", OUT_DIR)

if __name__ == "__main__":
    main()
