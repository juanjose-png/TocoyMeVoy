import React from "react";
import { cn } from "@/lib/utils";

interface LayoutProps {
    children: React.ReactNode;
    breadcrumb?: string;
}

export function Layout({ children, breadcrumb = "Solenium > Finanzas > Gestión de tarjetas" }: LayoutProps) {
    return (
        <div className="flex h-screen bg-background overflow-hidden">
            {/* Sidebar */}
            <aside className="w-64 bg-sidebar text-sidebar-foreground border-r border-sidebar-border hidden md:flex flex-col">
                <div className="p-6">
                    <h2 className="text-xl font-bold tracking-tight text-sidebar-primary">Solenium</h2>
                </div>
                <nav className="flex-1 px-4 space-y-2">
                    <div className="px-3 py-2 text-xs font-semibold uppercase tracking-wider opacity-50">
                        Administración
                    </div>
                    <a href="#" className="flex items-center gap-3 px-3 py-2 rounded-md bg-sidebar-accent text-sidebar-accent-foreground">
                        <span className="w-2 h-2 rounded-full bg-sidebar-primary" />
                        Tarjetas
                    </a>
                    <a href="#" className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-sidebar-accent transition-colors">
                        <span className="w-2 h-2 rounded-full border border-sidebar-foreground/30" />
                        Empleados
                    </a>
                </nav>
                <div className="p-4 border-t border-sidebar-border text-xs opacity-50">
                    v1.0.0-solenium
                </div>
            </aside>

            {/* Main Content */}
            <div className="flex-1 flex flex-col min-w-0">
                {/* Header with Gradient */}
                <header
                    className="h-16 flex items-center px-6 text-white shadow-lg z-10"
                    style={{ background: 'var(--soleniun-gradient)' }}
                >
                    <div className="flex items-center gap-4">
                        <button className="md:hidden">
                            <span className="sr-only">Menu</span>
                            {/* Menu Icon */}
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
                        </button>
                        <div className="text-sm font-medium tracking-wide">
                            {breadcrumb}
                        </div>
                    </div>
                    <div className="ml-auto flex items-center gap-4">
                        <div className="h-8 w-8 rounded-full bg-white/20 flex items-center justify-center border border-white/30">
                            U
                        </div>
                    </div>
                </header>

                {/* Page Content */}
                <main className="flex-1 overflow-y-auto p-6 relative">
                    {children}
                </main>
            </div>
        </div>
    );
}
