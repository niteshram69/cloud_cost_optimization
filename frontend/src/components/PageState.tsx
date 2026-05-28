interface PageStateProps {
  title: string;
  message?: string;
}

export function PageState({ title, message }: PageStateProps) {
  return (
    <div className="flex min-h-[300px] items-center justify-center rounded-xl border border-slate-200 bg-white p-8 text-center shadow-sm">
      <div>
        <p className="text-lg font-medium text-slate-900">{title}</p>
        {message ? <p className="mt-2 text-sm text-slate-600">{message}</p> : null}
      </div>
    </div>
  );
}
