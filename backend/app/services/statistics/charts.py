"""PNG con Agg sin interfaz gráfica; figuras liberadas tras cada exportación."""

import io
import textwrap

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D


class Charts:
    def __init__(self, prefix):
        self.prefix = prefix
        self.resources = {}

    def make(self, title, xlabel, ylabel, draw):
        if len(self.resources) >= 8:
            return None
        figure = Figure(figsize=(7.2, 4.8), dpi=130, layout="constrained")
        FigureCanvasAgg(figure)
        ax = figure.add_subplot()
        try:
            ax.set_title(textwrap.fill(title, 65), wrap=True)
            ax.set_xlabel(textwrap.fill(xlabel, 50))
            ax.set_ylabel(textwrap.fill(ylabel, 50))
            ax.spines[["top", "right"]].set_visible(False)
            draw(ax)
            output = io.BytesIO()
            figure.savefig(output, format="png")
            name = f"graficos/{self.prefix}_{len(self.resources) + 1}.png"
            self.resources[name] = output.getvalue()
            return name
        finally:
            figure.clear()

    def histogram(self, values, label):
        return self.make(
            f"Distribución de {label}",
            label,
            "Frecuencia",
            lambda ax: ax.hist(
                values, bins=min(30, max(1, int(np.sqrt(len(values))))), color="#386b87", edgecolor="white"
            ),
        )

    def frequencies(self, counts, label):
        return self.make(
            f"Frecuencias de {label}",
            label,
            "Observaciones válidas",
            lambda ax: (
                ax.bar([str(c) for c in counts], list(counts.values()), color="#386b87"),
                ax.tick_params(axis="x", labelrotation=35),
            ),
        )

    def box(self, arrays, labels, label):
        def draw(ax):
            ax.boxplot(arrays, tick_labels=labels, showmeans=True)
            ax.legend(
                handles=[
                    Line2D([], [], marker="^", color="green", linestyle="none", label="Media"),
                    Line2D([], [], color="#ff7f0e", label="Mediana"),
                ],
                loc="best",
            )

        return self.make(f"Diagrama de caja de {label}", "Grupo" if len(arrays) > 1 else "Observaciones", label, draw)

    def scatter(self, x, y, xlabel, ylabel):
        indexes = np.linspace(0, len(x) - 1, min(2000, len(x)), dtype=int)
        suffix = " (muestra visual uniforme de 2000 parejas)" if len(x) > 2000 else ""
        return self.make(
            f"{xlabel} y {ylabel}{suffix}",
            xlabel,
            ylabel,
            lambda ax: ax.scatter(np.asarray(x)[indexes], np.asarray(y)[indexes], alpha=0.5, s=12, color="#386b87"),
        )

    def matrix(self, matrix, labels):
        def draw(ax):
            im = ax.imshow(matrix, vmin=-1, vmax=1, cmap="RdBu_r")
            ax.set_xticks(range(len(labels)), labels, rotation=35, ha="right")
            ax.set_yticks(range(len(labels)), labels)
            ax.figure.colorbar(im, ax=ax, label="Coeficiente")

        return self.make("Matriz de correlaciones (N por pareja en tabla)", "", "", draw)

    def contingency(self, observed, rows, columns, row_label, column_label):
        def draw(ax):
            im = ax.imshow(observed, vmin=0, cmap="Blues")
            ax.set_xticks(range(len(columns)), columns, rotation=35, ha="right")
            ax.set_yticks(range(len(rows)), rows)
            ax.figure.colorbar(im, ax=ax, label="Frecuencia observada")

        return self.make("Tabla de contingencia observada", column_label, row_label, draw)
