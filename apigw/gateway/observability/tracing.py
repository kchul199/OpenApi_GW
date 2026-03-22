"""
OpenTelemetry Tracing setup.
"""
import os
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

def setup_tracing(app: FastAPI, app_name: str = "oag-gateway"):
    """
    Configure OpenTelemetry tracing for the FastAPI app.
    In a real production environment, this would export to an OTLP endpoint (Jaeger/Zipkin).
    Here we configure a ConsoleSpanExporter or OTLP based on ENV.
    """
    resource = Resource.create({"service.name": app_name})
    provider = TracerProvider(resource=resource)
    
    # Use OTLP Exporter if configured, otherwise fallback to Console
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        except ImportError:
            exporter = ConsoleSpanExporter()
    else:
        exporter = ConsoleSpanExporter()

    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/_health,/_ready,/metrics")
