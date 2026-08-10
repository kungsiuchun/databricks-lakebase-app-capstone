/**
 * Interactive Price Chart Module
 * Uses Lightweight Charts (TradingView library)
 */

class StockChart {
    constructor(containerId, symbol) {
        this.container = document.getElementById(containerId);
        this.symbol = symbol;
        this.chart = null;
        this.candleSeries = null;
        this.lineSeries = null;
        this.areaSeries = null;
        this.volumeSeries = null;
        this.currentChartType = 'candlestick';
        this.currentTimeframe = '3M';
        this.rawData = [];
        
        this.init();
    }
    
    init() {
        // Create chart instance
        this.chart = LightweightCharts.createChart(this.container, {
            width: this.container.clientWidth,
            height: 500,
            layout: {
                background: { color: '#ffffff' },
                textColor: '#333',
            },
            grid: {
                vertLines: { color: '#f0f0f0' },
                horzLines: { color: '#f0f0f0' },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: '#e0e0e0',
            },
            timeScale: {
                borderColor: '#e0e0e0',
                timeVisible: true,
                secondsVisible: false,
            },
        });
        
        // Create candlestick series by default
        this.candleSeries = this.chart.addSeries(LightweightCharts.CandlestickSeries, {
            upColor: '#10b981',
            downColor: '#ef4444',
            borderUpColor: '#10b981',
            borderDownColor: '#ef4444',
            wickUpColor: '#10b981',
            wickDownColor: '#ef4444',
        });
        
        // Create volume series
        this.volumeSeries = this.chart.addSeries(LightweightCharts.HistogramSeries, {
            color: '#3b82f6',
            priceFormat: {
                type: 'volume',
            },
            priceScaleId: 'volume',
        });
        
        this.volumeSeries.priceScale().applyOptions({
            scaleMargins: {
                top: 0.85,
                bottom: 0,
            },
        });

        // Handle window resize
        window.addEventListener('resize', () => {
            this.chart.applyOptions({
                width: this.container.clientWidth,
            });
        });
    }
    
    async loadData(timeframe) {
        this.currentTimeframe = timeframe;
        
        try {
            const days = this.getTimeframeDays(timeframe);
            console.log(`Loading chart data for ${this.symbol}, timeframe: ${timeframe}, days: ${days}`);
            // Fetch from backend API - data comes from Lakebase price_history table (if ticker is synced)
            // or directly from Massive API (for non-synced tickers)
            const response = await fetch(`/ticker/${this.symbol}/history?days=${days}&limit=1000`);
            
            if (!response.ok) {
                // Try to get error message from response body
                let errorMsg = `HTTP ${response.status}: ${response.statusText}`;
                try {
                    const errorData = await response.json();
                    if (errorData.error) {
                        errorMsg = errorData.error;
                    }
                } catch (e) {
                    // Couldn't parse error response
                }
                console.error('Chart data fetch failed:', errorMsg);
                throw new Error(errorMsg);
            }
            
            const data = await response.json();
            console.log(`Received ${data.records || 0} records for chart`);
            this.rawData = data.history || [];
            
            if (this.rawData.length === 0) {
                this.showError('No price history available for this ticker');
                return;
            }
            
            // Sort data by date ascending for chart
            this.rawData.sort((a, b) => new Date(a.date) - new Date(b.date));
            
            this.updateChart();
        } catch (error) {
            console.error('Error loading chart data:', error);
            this.showError(error.message || 'Failed to load chart data');
        }
    }
    
    getTimeframeDays(timeframe) {
        switch (timeframe) {
            case '1W': return 7;
            case '1M': return 30;
            case '3M': return 90;
            default: return 90;
        }
    }
    
    updateChart() {
        // Convert data to chart format
        const priceData = this.rawData.map(bar => ({
            time: bar.date,
            open: parseFloat(bar.open),
            high: parseFloat(bar.high),
            low: parseFloat(bar.low),
            close: parseFloat(bar.close),
        })).filter(bar =>
            Number.isFinite(bar.open) &&
            Number.isFinite(bar.high) &&
            Number.isFinite(bar.low) &&
            Number.isFinite(bar.close)
        );
        
        const volumeData = this.rawData.map(bar => {
            const close = parseFloat(bar.close);
            const open = parseFloat(bar.open);
            const color = close >= open ? '#10b98180' : '#ef444480';
            
            return {
                time: bar.date,
                value: parseFloat(bar.volume) || 0,
                color: color,
            };
        });
        
        // Update series based on chart type
        if (this.currentChartType === 'candlestick') {
            this.candleSeries.setData(priceData);
        } else if (this.currentChartType === 'line') {
            if (!this.lineSeries) {
                this.lineSeries = this.chart.addSeries(LightweightCharts.LineSeries, {
                    color: '#3b82f6',
                    lineWidth: 2,
                });
            }
            const lineData = priceData.map(bar => ({
                time: bar.time,
                value: bar.close,
            }));
            this.lineSeries.setData(lineData);
        } else if (this.currentChartType === 'area') {
            if (!this.areaSeries) {
                this.areaSeries = this.chart.addSeries(LightweightCharts.AreaSeries, {
                    topColor: '#3b82f680',
                    bottomColor: '#3b82f610',
                    lineColor: '#3b82f6',
                    lineWidth: 2,
                });
            }
            const areaData = priceData.map(bar => ({
                time: bar.time,
                value: bar.close,
            }));
            this.areaSeries.setData(areaData);
        }
        
        // Always update volume
        this.volumeSeries.setData(volumeData);
        
        // Fit content
        this.chart.timeScale().fitContent();
    }
    
    switchChartType(type) {
        this.currentChartType = type;
        
        // Remove all price series
        if (this.candleSeries) {
            this.chart.removeSeries(this.candleSeries);
            this.candleSeries = null;
        }
        if (this.lineSeries) {
            this.chart.removeSeries(this.lineSeries);
            this.lineSeries = null;
        }
        if (this.areaSeries) {
            this.chart.removeSeries(this.areaSeries);
            this.areaSeries = null;
        }
        
        // Create new series based on type
        if (type === 'candlestick') {
            this.candleSeries = this.chart.addSeries(LightweightCharts.CandlestickSeries, {
                upColor: '#10b981',
                downColor: '#ef4444',
                borderUpColor: '#10b981',
                borderDownColor: '#ef4444',
                wickUpColor: '#10b981',
                wickDownColor: '#ef4444',
            });
        } else if (type === 'line') {
            this.lineSeries = this.chart.addSeries(LightweightCharts.LineSeries, {
                color: '#3b82f6',
                lineWidth: 2,
            });
        } else if (type === 'area') {
            this.areaSeries = this.chart.addSeries(LightweightCharts.AreaSeries, {
                topColor: '#3b82f680',
                bottomColor: '#3b82f610',
                lineColor: '#3b82f6',
                lineWidth: 2,
            });
        }
        
        // Re-render with existing data
        this.updateChart();
    }
    
    showError(message) {
        this.container.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: center; height: 500px; color: #6b7280;">
                <div style="text-align: center;">
                    <div style="font-size: 48px; margin-bottom: 16px;">📊</div>
                    <div>${message}</div>
                </div>
            </div>
        `;
    }
}

// Chart UI Controller
class ChartController {
    constructor(symbol) {
        this.symbol = symbol;
        this.chart = null;
        
        this.initChart();
        this.initControls();
    }
    
    initChart() {
        this.chart = new StockChart('price-chart-container', this.symbol);
        // Load default timeframe (3 months)
        this.chart.loadData('3M');
    }
    
    initControls() {
        // Timeframe buttons
        const timeframeButtons = document.querySelectorAll('.timeframe-btn');
        timeframeButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                // Update active state
                timeframeButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                // Load new data
                const timeframe = btn.dataset.timeframe;
                this.chart.loadData(timeframe);
            });
        });
        
        // Chart type buttons
        const chartTypeButtons = document.querySelectorAll('.chart-type-btn');
        chartTypeButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                // Update active state
                chartTypeButtons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                // Switch chart type
                const chartType = btn.dataset.chartType;
                this.chart.switchChartType(chartType);
            });
        });
    }
}

// Export for use in detail.js
window.ChartController = ChartController;