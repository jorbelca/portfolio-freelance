#!/usr/bin/env python3
"""Aceptación real contra Docker. python3 verificar.py (desde 9/)."""
import argparse
import csv
import http.client
import io
import json
import socket
import subprocess
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent


def api(path="/api/estado", data=None, headers=None, esperado=200):
    c = http.client.HTTPConnection("127.0.0.1", 8089, timeout=25)
    try:
        c.request("POST" if data is not None else "GET", path, json.dumps(data) if data is not None else None,
                  {"Content-Type": "application/json", **(headers or {})})
        r = c.getresponse()
        body = r.read()
        assert r.status == esperado, (path, r.status, body[:300])
        return body.decode("utf-8-sig") if path.endswith("csv") or path == "/" else json.loads(body)
    finally:
        c.close()


def estado():
    return api()["ejecucion"]


def esperar(predicate, timeout=35):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        run = estado()
        if predicate(run):
            return run
        time.sleep(.15)
    raise AssertionError(("Tiempo agotado", estado()))


def crear(n=1, fallo="ninguno", pos=1):
    return api("/api/iniciar", {"opcion": "parque", "cantidad": n, "intervalo": 1, "fallo": fallo, "accion_fallo": pos}, esperado=201)


def control(run, accion):
    return api("/api/control", {"run_id": run["id"], "accion": accion})


def terminar():
    return esperar(lambda r: r["estado"].startswith("completada"))


def comprobar_informe(run, votos):
    report = api("/api/informe.json")
    assert report["ejecucion"]["id"] == run["id"]
    assert report["conciliacion"]["coinciden"], report["conciliacion"]
    assert len(report["destino"]["votos"]) == votos
    assert len({v["action_id"] for v in report["destino"]["votos"]}) == votos
    for action in run["acciones"]:
        if action["estado"] == "confirmada":
            assert action["ip"] == run["proxies"][action["proxy"]], action
    return report


def interno():
    from app import PROXIES, csv_informe, rpc
    print("Aceptación en Docker: HTTP real por Squid", flush=True)
    run = estado()
    assert not run or run["estado"] not in ("en curso", "pausada", "interrumpida"), "Hay una ejecución activa; termina o cancélala primero"
    api("/", esperado=200)
    for patch in ({"cantidad": 0}, {"cantidad": 101}, {"cantidad": True}, {"intervalo": .9},
                  {"intervalo": float('nan')}, {"opcion": "desconocida"}, {"opcion": []}, {"accion_fallo": 0}):
        cfg = {"opcion": "parque", "cantidad": 12, "intervalo": 1, "fallo": "ninguno", "accion_fallo": 5, **patch}
        api("/api/iniciar", cfg, esperado=400)
    api("/api/iniciar", {}, {"Origin": "http://otro-sitio.example"}, esperado=403)
    api("/api/estado", headers={"Host": "otro-sitio.example"}, esperado=403)
    try:
        socket.create_connection(("destino", 8090), timeout=2).close()
    except OSError:
        pass
    else:
        raise AssertionError("La app puede acceder directamente al destino")
    for proxy in PROXIES:
        assert rpc(proxy, "GET", "/health")[0] == 200
        c = http.client.HTTPConnection(proxy, 3128, timeout=5)
        c.request("GET", "http://example.com/")
        assert c.getresponse().status == 403
        c.close()
    print("✓ Entradas, origen, aislamiento y ACL de los tres proxies", flush=True)

    crear(12)
    run = terminar()
    report = comprobar_informe(run, 12)
    assert [a["proxy"] for a in run["acciones"]] == ["proxy-a"]*5 + ["proxy-b"]*5 + ["proxy-c"]*2
    assert len({v["ip"] for v in report["destino"]["votos"]}) == 3
    assert len(list(csv.reader(io.StringIO(api("/api/informe.csv"))))) == 13
    action = run["acciones"][0]
    post = {"action_id": action["id"], "opcion": "parque", "fallo": "ninguno"}
    assert rpc("proxy-a", "POST", "/votes", post)[0] == 200
    assert rpc("proxy-a", "POST", "/votes", {**post, "opcion": "biblioteca"})[0] == 409
    assert rpc("proxy-a", "GET", "/runs/"+run["id"])[1]["votos"][0]["opcion"] == "parque"
    print("✓ 12 acciones / tres IP observadas / reparto 5–5–2 / deduplicación / exportaciones", flush=True)

    crear(16, "temporal", 5)
    run = terminar()
    comprobar_informe(run, 16)
    assert run["acciones"][15]["proxy"] == "proxy-a"
    assert len(run["acciones"][4]["intentos"]) == 2
    assert all(a["proxy"] == "proxy-a" for a in run["acciones"][:5])
    assert all(i["proxy"] == "proxy-a" for i in run["acciones"][4]["intentos"])
    for a, b in zip([i for a in run["acciones"] for i in a["intentos"]], [i for a in run["acciones"] for i in a["intentos"]][1:]):
        from datetime import datetime
        assert (datetime.fromisoformat(b["inicio"])-datetime.fromisoformat(a["inicio"])).total_seconds() >= .99
    print("✓ Límites 5/6/10/11/16 y reintento de la acción 5; intervalo respetado", flush=True)

    for fallo in ("respuesta_perdida", "persistente", "limite", "validacion"):
        crear(fallo=fallo)
        run = terminar()
        ok = fallo not in ("persistente", "validacion")
        report = comprobar_informe(run, 1 if ok else 0)
        assert run["acciones"][0]["estado"] == ("confirmada" if ok else "fallida")
        count = len(run["acciones"][0]["intentos"])
        assert count == {"respuesta_perdida": 1, "persistente": 3, "limite": 2, "validacion": 1}[fallo]
        if fallo == "limite":
            from datetime import datetime
            tries = run["acciones"][0]["intentos"]
            assert (datetime.fromisoformat(tries[1]["inicio"])-datetime.fromisoformat(tries[0]["fin"])).total_seconds() >= 1.99
        print("✓ " + fallo, flush=True)
    for fallo in ("incierta", "limite_invalido", "rechazo"):
        crear(fallo=fallo)
        run = esperar(lambda r: r["estado"] == "pausada")
        assert run["acciones"][0]["estado"] == "incierta"
        if fallo == "incierta":
            control(run, "continuar")
            run = terminar()
            comprobar_informe(run, 1)
            assert len(run["acciones"][0]["intentos"]) == 1
        else:
            control(run, "cancelar")
        print("✓ Pausa ante " + fallo, flush=True)

    run = crear(5)
    api("/api/iniciar", run["config"], esperado=409)
    esperar(lambda r: r["acciones"][0]["estado"] == "confirmada")
    control(run, "pausar")
    time.sleep(.5)
    first = estado()
    time.sleep(1.4)
    assert first["acciones"] == estado()["acciones"], "Se envió durante la pausa"
    control(run, "continuar")
    esperar(lambda r: r["acciones"][1]["estado"] == "confirmada")
    control(run, "cancelar")
    time.sleep(.5)
    cancelled = estado()
    time.sleep(1.4)
    assert cancelled["acciones"] == estado()["acciones"]
    assert any(a["estado"] == "cancelada" for a in cancelled["acciones"])
    print("✓ Inicio duplicado, pausa, continuación y cancelación", flush=True)

    content = csv_informe({"ejecucion": {"acciones": [{"id": "=1+1", "posicion": 1, "proxy": "proxy-a", "estado": "fallida", "ip": None, "intentos": [], "resultado": "  @cmd"}]}}).decode('utf-8-sig')
    assert "'=1+1" in content and "'  @cmd" in content
    print("✓ CSV neutraliza fórmulas", flush=True)


def compose(*args):
    return subprocess.run(["docker", "compose", "-f", str(BASE / "compose.yaml"), *args], check=True, text=True, capture_output=True).stdout


def comprobar_red():
    container = compose("ps", "-q", "destino").strip()
    info = json.loads(subprocess.check_output(["docker", "inspect", container], text=True))[0]
    ip = next(iter(info["NetworkSettings"]["Networks"].values()))["IPAddress"]
    code = f"""import socket
try:
    socket.create_connection(({ip!r},8090),timeout=2).close()
except OSError:
    pass
else:
    raise AssertionError('Acceso directo al destino permitido')
"""
    compose("exec", "-T", "app", "python", "-c", code)
    code = """import json,http.client
from app import leer,rpc
run=leer(); a=run['acciones'][0]
c=http.client.HTTPConnection(a['proxy'],3128,timeout=5)
c.request('POST','http://destino:8090/votes',json.dumps({'action_id':a['id'],'opcion':run['config']['opcion'],'fallo':a['fallo']}),{'Content-Type':'application/json','X-Forwarded-For':'203.0.113.99'})
r=c.getresponse(); assert r.status==200; r.read(); c.close()
report=rpc(a['proxy'],'GET','/runs/'+run['id'])[1]
assert report['solicitudes'][-1]['ip']==rpc(a['proxy'],'GET','/health')[1]['ip_observada']
assert report['solicitudes'][-1]['ip']!='203.0.113.99'
"""
    compose("exec", "-T", "app", "python", "-c", code)
    api("/api/control", {"run_id": [], "accion": "pausar"}, esperado=400)
    print("✓ Acceso directo por IP bloqueado; cabecera falsa ignorada; control inválido rechazado", flush=True)


def externo():
    # El acceso a Docker se queda en el host; ningún contenedor monta su socket.
    subprocess.run(["docker", "compose", "-f", str(BASE / "compose.yaml"), "exec", "-T", "app", "python", "verificar.py", "--interno"], check=True)
    run = crear(6)
    try:
        # Acción 6 aún no se ha enviado; se fuerza la caída de su ruta.
        compose("stop", "proxy-b")
        run = esperar(lambda r: r["estado"] == "pausada", timeout=45)
        assert run["acciones"][5]["estado"] == "incierta"
        assert run["acciones"][5]["proxy"] == "proxy-b"
        compose("start", "proxy-b")
        time.sleep(2)
        control(run, "continuar")
        run = terminar()
        comprobar_informe(run, 6)
        print("✓ Caída de proxy-b, pausa y recuperación sin duplicados", flush=True)
    finally:
        compose("start", "proxy-b")

    # Respuesta lenta para interrumpir una acción después de que el destino haya escrito.
    run = crear(3, "lenta")
    esperar(lambda r: r["acciones"][0]["estado"] == "en curso")
    time.sleep(.5)
    compose("kill", "-s", "SIGKILL", "app")
    compose("up", "-d", "--wait", "--no-deps", "--force-recreate", "app")
    limite = time.monotonic()+20
    while True:
        try:
            run = estado()
            break
        except (OSError, http.client.HTTPException):
            assert time.monotonic() < limite
            time.sleep(.3)
    assert run["estado"] == "interrumpida"
    assert run["acciones"][0]["estado"] == "incierta"
    time.sleep(1)
    assert estado()["estado"] == "interrumpida", "Se reanudó automáticamente"
    control(run, "continuar")
    run = terminar()
    comprobar_informe(run, 3)
    assert len(run["acciones"][0]["intentos"]) == 1
    print("✓ Reinicio durante un envío: estado persistido y reconciliación", flush=True)

    run_id = run["id"]
    compose("up", "-d", "--wait", "--no-deps", "--force-recreate", "destino", "proxy-a", "proxy-b", "proxy-c", "app")
    assert estado()["id"] == run_id
    assert len(api("/api/informe.json")["destino"]["votos"]) == 3
    crear()
    run = terminar()
    comprobar_informe(run, 1)
    print("✓ Recreación: ambos volúmenes conservados y correspondencia de IP verificada", flush=True)
    comprobar_red()
    print("ACEPTACIÓN COMPLETA", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interno", action="store_true")
    args = parser.parse_args()
    interno() if args.interno else externo()
