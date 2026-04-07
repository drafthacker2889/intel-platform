import React, { useEffect, useMemo, useState } from 'react';
import './App.css';

type HealthState = 'online' | 'offline' | 'degraded';

type ServiceCard = {
  name: string;
  port?: number;
  status: string;
  health: HealthState;
  details: string;
};

async function probe(url: string): Promise<boolean> {
  try {
    const response = await fetch(url, { cache: 'no-store' });
    return response.ok;
  } catch {
    return false;
  }
}

function App() {
  const [gatewayHealthy, setGatewayHealthy] = useState<boolean>(false);
  const [brainHealthy, setBrainHealthy] = useState<boolean>(false);
  const [lastUpdated, setLastUpdated] = useState<string>('pending');

  useEffect(() => {
    let mounted = true;

    const refreshHealth = async () => {
      const [gatewayStatus, brainStatus] = await Promise.all([
        probe('/health'),
        probe('/brain/health'),
      ]);

      if (!mounted) {
        return;
      }

      setGatewayHealthy(gatewayStatus);
      setBrainHealthy(brainStatus);
      setLastUpdated(new Date().toLocaleTimeString());
    };

    refreshHealth();
    const timer = window.setInterval(refreshHealth, 5000);

    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  const services = useMemo<ServiceCard[]>(() => {
    const gatewayState: HealthState = gatewayHealthy ? 'online' : 'offline';
    const brainState: HealthState = brainHealthy ? 'online' : 'offline';
    const pipelineState: HealthState = gatewayHealthy && brainHealthy ? 'online' : 'degraded';

    return [
      {
        name: 'Gateway',
        port: 8080,
        status: gatewayHealthy ? 'Serving ingress' : 'Unavailable',
        health: gatewayState,
        details: 'Single public ingress and routing boundary',
      },
      {
        name: 'Brain',
        port: 8082,
        status: brainHealthy ? 'Scoring active' : 'No heartbeat',
        health: brainState,
        details: 'Entity extraction and risk scoring worker',
      },
      {
        name: 'Pipeline',
        status: pipelineState === 'online' ? 'Flowing end-to-end' : 'Partial degradation',
        health: pipelineState,
        details: 'Queue to index path readiness',
      },
      {
        name: 'Collector',
        port: 8081,
        status: 'Collecting',
        health: 'degraded',
        details: 'Crawler state is inferred until per-service metrics are exposed',
      },
      {
        name: 'Sanitizer',
        status: 'Sanitizing',
        health: 'degraded',
        details: 'Worker health endpoint planned in next hardening pass',
      },
      {
        name: 'Storage',
        status: 'Indexing and graph persistence',
        health: 'degraded',
        details: 'Elasticsearch, Neo4j, and Redis monitored via compose and logs',
      },
    ];
  }, [brainHealthy, gatewayHealthy]);

  return (
    <main className="app-shell">
      <section className="hero">
        <p className="badge">Intel Platform</p>
        <h1>Operational Intelligence Fabric</h1>
        <p>
          Real-time collection, sanitization, risk scoring, and indexing across your distributed stack.
        </p>
        <p className="meta">Last updated: {lastUpdated}</p>
      </section>

      <section className="grid">
        {services.map((service) => (
          <article className="card" key={service.name}>
            <h2>{service.name}</h2>
            <p className={`status status-${service.health}`}>{service.status}</p>
            <p className="port">{service.port ? `Port ${service.port}` : 'Worker mode'}</p>
            <p className="details">{service.details}</p>
          </article>
        ))}
      </section>
    </main>
  );
}

export default App;
