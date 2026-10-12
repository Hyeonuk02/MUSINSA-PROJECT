# Istio (Phase 1)

## 버전

| 항목 | 값 |
|---|---|
| istioctl / control plane / data plane | `1.31.1` |
| 설치 프로파일 | `default` (istiod + istio-ingressgateway) |
| 지원 Kubernetes | 1.32 ~ 1.36 → 클러스터는 `v1.35.8` |

설치 경로: `brew install istioctl` (1.31.1, arm64)

## 설치

```bash
istioctl install -f deploy/k8s/istio/istio-install.yaml -y
```

`istio-system` 네임스페이스는 이 명령이 만든다.
설정을 바꾼 뒤에도 **같은 명령을 다시 실행**하면 된다 (1.4의 tracing extensionProvider,
1.5의 `outboundTrafficPolicy: REGISTRY_ONLY`가 `istio-install.yaml`에 추가될 예정).

## sidecar 주입

```bash
kubectl label namespace legacy new istio-injection=enabled --overwrite
```

`observability`, `verify`, `default`는 `istio-injection=disabled`로 **명시**했다.
메시에 넣을 이유가 없고(OTel Collector·Jaeger는 Istio가 OTLP로 직접 호출),
라벨이 없으면 `istioctl analyze`가 매번 IST0102 Info를 낸다. 나중에 필요하면 되돌리면 된다.

주입 결과 예시:

```
$ kubectl get pod inject-check -n legacy
NAME           READY   STATUS    RESTARTS   AGE
inject-check   2/2     Running   0          5s
```

**주의 — `istio-proxy`는 initContainer 자리에 있다.**
Istio 1.31은 Kubernetes native sidecar(`restartPolicy: Always` initContainer)를 기본으로 쓴다.

```
$ kubectl get pod inject-check -n legacy -o jsonpath='{range .spec.initContainers[*]}{.name}{"\n"}{end}'
istio-init
istio-proxy
```

`.spec.containers`만 세면 sidecar가 없는 것처럼 보이므로, 이후 단계에서 주입을 확인할 때는
`READY 2/2` 또는 `initContainers`를 봐야 한다. `kubectl logs -c istio-proxy`는 그대로 동작한다.

## Ingress Gateway

kind에는 LoadBalancer 구현이 없어 기본 `type: LoadBalancer`면 Service가 Pending으로 남는다.
`istio-install.yaml`에서 NodePort로 고정하고, 1.1에서 만든 호스트 포트 매핑에 맞췄다.

```
host 80  -> node 30080 -> istio-ingressgateway :80  -> targetPort 8080
host 443 -> node 30443 -> istio-ingressgateway :443 -> targetPort 8443
```

`nodeSelector: ingress-ready=true`로 포트 매핑이 걸린 노드에 고정한다.
`Gateway` / `VirtualService` 리소스는 1.6에서 만든다.

## 이 프로젝트에서 Istio의 역할

미러링 배달(1.6) · REGISTRY_ONLY guardrail(1.5) · proxy 스팬(1.4) 셋뿐이다.
격리 경계는 Istio가 아니라 Kubernetes NetworkPolicy다.
canary, retry, circuit breaker, mTLS 튜닝, Egress Gateway, Kiali는 쓰지 않는다.
