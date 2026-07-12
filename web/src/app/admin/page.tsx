"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, isApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  AdminTab,
  AdminUser,
  AdminUserCreate,
  AdminUserUpdate,
  RolePermission,
  RolePermissionMatrix,
  TabCatalog,
} from "@/types/api";

const ROLES = [
  { value: "admin", label: "관리자" },
  { value: "manager", label: "매니저" },
  { value: "viewer", label: "뷰어" },
];

type AdminPanel = "users" | "tabs";

type UserForm = {
  name: string;
  email: string;
  login_id: string;
  password: string;
  role: string;
  status: boolean;
};

function blankUserForm(): UserForm {
  return {
    name: "",
    email: "",
    login_id: "",
    password: "",
    role: "viewer",
    status: true,
  };
}

function roleLabel(role: string): string {
  return ROLES.find((item) => item.value === role)?.label ?? role;
}

function formatDate(value: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function toCreatePayload(form: UserForm): AdminUserCreate {
  return {
    name: form.name.trim(),
    email: form.email.trim(),
    login_id: form.login_id.trim() || null,
    password: form.password || null,
    role: form.role,
    status: form.status,
  };
}

function toUpdatePayload(form: UserForm): AdminUserUpdate {
  return {
    name: form.name.trim(),
    email: form.email.trim(),
    login_id: form.login_id.trim() || null,
    password: form.password || undefined,
    role: form.role,
    status: form.status,
  };
}

function errorText(error: unknown): string {
  if (isApiError(error)) return error.detail || error.message;
  return error instanceof Error ? error.message : "알 수 없는 오류";
}

function permissionKey(role: string, tabId: string): string {
  return `${role}|${tabId}`;
}

function buildPermissionDraft(matrix?: RolePermissionMatrix): Record<string, boolean> {
  const draft: Record<string, boolean> = {};
  for (const item of matrix?.permissions ?? []) {
    draft[permissionKey(item.role, item.tab_id)] = item.can_view;
  }
  return draft;
}

function buildTabDraft(catalog?: TabCatalog): Record<string, boolean> {
  return { ...(catalog?.statuses ?? {}) };
}

export default function AdminPage() {
  const { token, user, userLoading, logout, refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const [panel, setPanel] = useState<AdminPanel>("users");
  const [createForm, setCreateForm] = useState<UserForm>(() => blankUserForm());
  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [editForm, setEditForm] = useState<UserForm>(() => blankUserForm());
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [permissionDraft, setPermissionDraft] = useState<Record<string, boolean>>({});
  const [tabDraft, setTabDraft] = useState<Record<string, boolean>>({});

  const isAdmin = user?.role === "admin";

  function handleError(err: unknown): void {
    if (isApiError(err) && err.status === 401) logout();
    setError(errorText(err));
  }

  const usersQuery = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => api.listAdminUsers(token ?? ""),
    enabled: Boolean(token && isAdmin),
    retry: false,
  });

  const rolePermissionsQuery = useQuery({
    queryKey: ["admin-role-permissions"],
    queryFn: () => api.getRolePermissions(token ?? ""),
    enabled: Boolean(token && isAdmin),
    retry: false,
  });

  const tabCatalogQuery = useQuery({
    queryKey: ["tab-catalog"],
    queryFn: () => api.getTabCatalog(),
  });

  useEffect(() => {
    setPermissionDraft(buildPermissionDraft(rolePermissionsQuery.data));
  }, [rolePermissionsQuery.data]);

  useEffect(() => {
    setTabDraft(buildTabDraft(tabCatalogQuery.data));
  }, [tabCatalogQuery.data]);

  const createUser = useMutation({
    mutationFn: (payload: AdminUserCreate) => api.createAdminUser(token ?? "", payload),
    onSuccess: () => {
      setCreateForm(blankUserForm());
      setNotice("사용자를 등록했습니다.");
      setError("");
      void queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: handleError,
  });

  const updateUser = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: AdminUserUpdate }) =>
      api.updateAdminUser(token ?? "", id, payload),
    onSuccess: () => {
      setEditing(null);
      setNotice("사용자 정보를 저장했습니다.");
      setError("");
      void queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      void refreshUser();
    },
    onError: handleError,
  });

  const deleteUser = useMutation({
    mutationFn: (id: number) => api.deleteAdminUser(token ?? "", id),
    onSuccess: () => {
      setNotice("사용자를 제거했습니다.");
      setError("");
      void queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: handleError,
  });

  const updatePermissions = useMutation({
    mutationFn: (permissions: RolePermission[]) =>
      api.updateRolePermissions(token ?? "", permissions),
    onSuccess: (matrix) => {
      setPermissionDraft(buildPermissionDraft(matrix));
      setNotice("역할별 탭 권한을 저장했습니다.");
      setError("");
      void queryClient.invalidateQueries({ queryKey: ["admin-role-permissions"] });
      void refreshUser();
    },
    onError: handleError,
  });

  const updateTabs = useMutation({
    mutationFn: (statuses: Record<string, boolean>) =>
      api.updateTabStatus(token ?? "", statuses),
    onSuccess: (catalog) => {
      setTabDraft(buildTabDraft(catalog));
      setNotice("탭 상태를 저장했습니다.");
      setError("");
      queryClient.setQueryData(["tab-catalog"], catalog);
    },
    onError: handleError,
  });

  const users = usersQuery.data?.users ?? [];
  const matrix = rolePermissionsQuery.data;
  const catalog = tabCatalogQuery.data;

  const hasPermissionChanges = useMemo(() => {
    const original = buildPermissionDraft(matrix);
    const keys = new Set([...Object.keys(original), ...Object.keys(permissionDraft)]);
    return [...keys].some((key) => original[key] !== permissionDraft[key]);
  }, [matrix, permissionDraft]);

  const hasTabChanges = useMemo(() => {
    const original = buildTabDraft(catalog);
    const keys = new Set([...Object.keys(original), ...Object.keys(tabDraft)]);
    return [...keys].some((key) => original[key] !== tabDraft[key]);
  }, [catalog, tabDraft]);

  function openEdit(userRow: AdminUser): void {
    setEditing(userRow);
    setEditForm({
      name: userRow.name,
      email: userRow.email,
      login_id: userRow.login_id ?? "",
      password: "",
      role: userRow.role,
      status: userRow.status,
    });
    setError("");
    setNotice("");
  }

  function submitCreate(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    createUser.mutate(toCreatePayload(createForm));
  }

  function submitEdit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!editing) return;
    updateUser.mutate({ id: editing.id, payload: toUpdatePayload(editForm) });
  }

  function resetPassword(userRow: AdminUser): void {
    updateUser.mutate({ id: userRow.id, payload: { reset_password: true } });
  }

  function removeUser(userRow: AdminUser): void {
    if (!window.confirm(`${userRow.name} 사용자를 제거할까요?`)) return;
    deleteUser.mutate(userRow.id);
  }

  function getPermission(role: string, tabId: string): boolean {
    return Boolean(permissionDraft[permissionKey(role, tabId)]);
  }

  function setPermission(role: string, tab: AdminTab, checked: boolean): void {
    if (role === "admin") return;
    if (tab.admin_only) return;
    setPermissionDraft((current) => ({
      ...current,
      [permissionKey(role, tab.id)]: checked,
    }));
  }

  function savePermissions(): void {
    if (!matrix) return;
    const permissions = matrix.roles.flatMap((role) =>
      matrix.groups.flatMap((group) =>
        group.tabs.map((tab) => ({
          role: role.value,
          tab_id: tab.id,
          can_view: getPermission(role.value, tab.id),
        }))
      )
    );
    updatePermissions.mutate(permissions);
  }

  function setTabStatus(tabId: string, checked: boolean): void {
    setTabDraft((current) => ({ ...current, [tabId]: checked }));
  }

  if (!token) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-8 text-sm text-gray-600 shadow-sm">
        로그인 후 관리자 탭을 사용할 수 있습니다.
      </div>
    );
  }

  if (userLoading || !user) {
    return <div className="py-20 text-center text-gray-500">관리자 정보 확인 중...</div>;
  }

  if (!isAdmin) {
    return (
      <div className="rounded-lg border border-red-100 bg-red-50 p-8 text-sm text-red-700">
        관리자 권한이 필요합니다.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">관리자</h1>
          <p className="text-sm text-gray-500">{user.name} · {roleLabel(user.role)}</p>
        </div>
        <div className="inline-flex rounded-lg border border-gray-200 bg-white p-1 shadow-sm">
          <button
            type="button"
            onClick={() => setPanel("users")}
            className={`rounded-md px-4 py-2 text-sm font-medium ${
              panel === "users"
                ? "bg-indigo-600 text-white"
                : "text-gray-600 hover:bg-gray-50"
            }`}
          >
            사용자 관리
          </button>
          <button
            type="button"
            onClick={() => setPanel("tabs")}
            className={`rounded-md px-4 py-2 text-sm font-medium ${
              panel === "tabs"
                ? "bg-indigo-600 text-white"
                : "text-gray-600 hover:bg-gray-50"
            }`}
          >
            탭 관리
          </button>
        </div>
      </div>

      {(notice || error) && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            error
              ? "border-red-200 bg-red-50 text-red-700"
              : "border-emerald-200 bg-emerald-50 text-emerald-700"
          }`}
        >
          {error || notice}
        </div>
      )}

      {panel === "users" ? (
        <div className="space-y-6">
          <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="text-base font-semibold text-gray-900">사용자 등록</h2>
            <form onSubmit={submitCreate} className="mt-4 grid gap-3 lg:grid-cols-6">
              <input
                value={createForm.name}
                onChange={(e) =>
                  setCreateForm((current) => ({ ...current, name: e.target.value }))
                }
                placeholder="이름"
                required
                className="rounded-md border border-gray-300 px-3 py-2 text-sm lg:col-span-1"
              />
              <input
                value={createForm.email}
                onChange={(e) =>
                  setCreateForm((current) => ({ ...current, email: e.target.value }))
                }
                type="email"
                placeholder="이메일"
                required
                className="rounded-md border border-gray-300 px-3 py-2 text-sm lg:col-span-2"
              />
              <input
                value={createForm.login_id}
                onChange={(e) =>
                  setCreateForm((current) => ({ ...current, login_id: e.target.value }))
                }
                placeholder="아이디"
                className="rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
              <input
                value={createForm.password}
                onChange={(e) =>
                  setCreateForm((current) => ({ ...current, password: e.target.value }))
                }
                type="password"
                placeholder="초기 비밀번호"
                className="rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
              <div className="flex gap-2">
                <select
                  value={createForm.role}
                  onChange={(e) =>
                    setCreateForm((current) => ({ ...current, role: e.target.value }))
                  }
                  className="min-w-0 flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm"
                >
                  {ROLES.map((role) => (
                    <option key={role.value} value={role.value}>
                      {role.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() =>
                    setCreateForm((current) => ({ ...current, status: !current.status }))
                  }
                  className={`rounded-md border px-3 py-2 text-sm ${
                    createForm.status
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-gray-200 bg-gray-50 text-gray-500"
                  }`}
                >
                  {createForm.status ? "활성" : "비활성"}
                </button>
              </div>
              <button
                type="submit"
                disabled={createUser.isPending}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60 lg:col-start-6"
              >
                {createUser.isPending ? "등록 중" : "등록"}
              </button>
            </form>
          </section>

          <section className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
            <div className="border-b border-gray-200 px-5 py-4">
              <h2 className="text-base font-semibold text-gray-900">사용자 목록</h2>
            </div>
            <div className="max-h-[52vh] overflow-y-auto">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="sticky top-0 z-10 bg-gray-50 text-xs uppercase text-gray-500">
                  <tr>
                    <th className="px-4 py-3 text-left">상태</th>
                    <th className="px-4 py-3 text-left">이름</th>
                    <th className="px-4 py-3 text-left">이메일</th>
                    <th className="px-4 py-3 text-left">아이디</th>
                    <th className="px-4 py-3 text-left">비밀번호</th>
                    <th className="px-4 py-3 text-left">역할</th>
                    <th className="px-4 py-3 text-left">최근 로그인</th>
                    <th className="px-4 py-3 text-right">작업</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 bg-white">
                  {usersQuery.isLoading ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                        사용자 목록 로딩 중...
                      </td>
                    </tr>
                  ) : users.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                        등록된 사용자가 없습니다.
                      </td>
                    </tr>
                  ) : (
                    users.map((row) => (
                      <tr key={row.id}>
                        <td className="px-4 py-3">
                          <span
                            className={`rounded-full px-2 py-1 text-xs font-medium ${
                              row.status
                                ? "bg-emerald-50 text-emerald-700"
                                : "bg-gray-100 text-gray-500"
                            }`}
                          >
                            {row.status ? "활성" : "비활성"}
                          </span>
                        </td>
                        <td className="max-w-[140px] truncate px-4 py-3 font-medium text-gray-900">
                          {row.name}
                        </td>
                        <td className="max-w-[220px] truncate px-4 py-3 text-gray-600">
                          {row.email}
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-gray-600">
                          {row.login_id || "미설정"}
                        </td>
                        <td className="px-4 py-3 text-gray-600">
                          {row.has_password ? "설정됨" : "대기"}
                        </td>
                        <td className="px-4 py-3 text-gray-600">{roleLabel(row.role)}</td>
                        <td className="whitespace-nowrap px-4 py-3 text-gray-500">
                          {formatDate(row.last_login_at)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => openEdit(row)}
                              className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
                            >
                              편집
                            </button>
                            {row.has_password && (
                              <button
                                type="button"
                                onClick={() => resetPassword(row)}
                                className="rounded-md border border-amber-200 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-50"
                              >
                                초기화
                              </button>
                            )}
                            {user.id !== row.id && (
                              <button
                                type="button"
                                onClick={() => removeUser(row)}
                                className="rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50"
                              >
                                제거
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
            <div className="flex items-center justify-between gap-4 border-b border-gray-200 px-5 py-4">
              <h2 className="text-base font-semibold text-gray-900">역할별 탭 권한</h2>
              <button
                type="button"
                onClick={savePermissions}
                disabled={!hasPermissionChanges || updatePermissions.isPending}
                className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-40"
              >
                {updatePermissions.isPending ? "저장 중" : "권한 저장"}
              </button>
            </div>
            <div className="max-h-[52vh] overflow-y-auto">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="sticky top-0 z-10 bg-gray-50 text-xs uppercase text-gray-500">
                  <tr>
                    <th className="px-4 py-3 text-left">탭</th>
                    {matrix?.roles.map((role) => (
                      <th key={role.value} className="px-4 py-3 text-center">
                        {role.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 bg-white">
                  {rolePermissionsQuery.isLoading || !matrix ? (
                    <tr>
                      <td colSpan={4} className="px-4 py-8 text-center text-gray-500">
                        권한 로딩 중...
                      </td>
                    </tr>
                  ) : (
                    matrix.groups.flatMap((group) => [
                      <tr key={group.id} className="bg-gray-50">
                        <td
                          colSpan={matrix.roles.length + 1}
                          className="px-4 py-2 text-xs font-semibold text-gray-500"
                        >
                          {group.label}
                        </td>
                      </tr>,
                      ...group.tabs.map((tab) => (
                        <tr key={tab.id}>
                          <td className="px-4 py-3">
                            <span className="font-medium text-gray-900">{tab.label}</span>
                            {tab.admin_only && (
                              <span className="ml-2 text-xs text-red-600">admin 고정</span>
                            )}
                          </td>
                          {matrix.roles.map((role) => {
                            const locked = role.value === "admin" || tab.admin_only;
                            return (
                              <td key={role.value} className="px-4 py-3 text-center">
                                <input
                                  type="checkbox"
                                  checked={getPermission(role.value, tab.id)}
                                  disabled={locked || updatePermissions.isPending}
                                  onChange={(e) =>
                                    setPermission(role.value, tab, e.target.checked)
                                  }
                                  className="h-4 w-4 rounded border-gray-300 text-indigo-600"
                                />
                              </td>
                            );
                          })}
                        </tr>
                      )),
                    ])
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      ) : (
        <section className="rounded-lg border border-gray-200 bg-white shadow-sm">
          <div className="flex items-center justify-between gap-4 border-b border-gray-200 px-5 py-4">
            <h2 className="text-base font-semibold text-gray-900">탭 관리</h2>
            <button
              type="button"
              onClick={() => updateTabs.mutate(tabDraft)}
              disabled={!hasTabChanges || updateTabs.isPending}
              className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-40"
            >
              {updateTabs.isPending ? "저장 중" : "변경사항 적용"}
            </button>
          </div>
          <div className="max-h-[70vh] overflow-y-auto p-5">
            {tabCatalogQuery.isLoading || !catalog ? (
              <div className="py-12 text-center text-gray-500">탭 상태 로딩 중...</div>
            ) : (
              <div className="space-y-5">
                {catalog.groups.map((group) => (
                  <div key={group.id}>
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
                      {group.label}
                    </h3>
                    <div className="divide-y divide-gray-100 rounded-lg border border-gray-200">
                      {group.tabs.map((tab) => {
                        const enabled = tabDraft[tab.id] !== false;
                        return (
                          <div
                            key={tab.id}
                            className="flex items-center justify-between gap-4 px-4 py-3"
                          >
                            <div className="min-w-0">
                              <div className="font-medium text-gray-900">{tab.label}</div>
                              <div className="truncate text-xs text-gray-500">
                                {tab.route}
                              </div>
                            </div>
                            <div className="flex items-center gap-3">
                              <span
                                className={`text-sm font-medium ${
                                  enabled ? "text-emerald-700" : "text-red-600"
                                }`}
                              >
                                {enabled ? "사용중" : "미사용"}
                              </span>
                              <button
                                type="button"
                                onClick={() => setTabStatus(tab.id, !enabled)}
                                aria-pressed={enabled}
                                className={`relative h-7 w-12 rounded-full transition ${
                                  enabled ? "bg-emerald-500" : "bg-gray-300"
                                }`}
                              >
                                <span
                                  className={`absolute top-1 h-5 w-5 rounded-full bg-white transition ${
                                    enabled ? "left-6" : "left-1"
                                  }`}
                                />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      )}

      {editing && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center"
        >
          <div
            className="absolute inset-0 bg-black/40"
            aria-hidden="true"
            onClick={() => setEditing(null)}
          />
          <form
            onSubmit={submitEdit}
            className="relative z-10 w-full max-w-md space-y-4 rounded-xl bg-white p-6 shadow-2xl"
          >
            <h2 className="text-lg font-semibold text-gray-900">사용자 편집</h2>
            <input
              value={editForm.name}
              onChange={(e) =>
                setEditForm((current) => ({ ...current, name: e.target.value }))
              }
              required
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              value={editForm.email}
              onChange={(e) =>
                setEditForm((current) => ({ ...current, email: e.target.value }))
              }
              type="email"
              required
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              value={editForm.login_id}
              onChange={(e) =>
                setEditForm((current) => ({ ...current, login_id: e.target.value }))
              }
              placeholder="아이디"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
            <input
              value={editForm.password}
              onChange={(e) =>
                setEditForm((current) => ({ ...current, password: e.target.value }))
              }
              type="password"
              placeholder="새 비밀번호"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
            <div className="grid grid-cols-2 gap-3">
              <select
                value={editForm.role}
                onChange={(e) =>
                  setEditForm((current) => ({ ...current, role: e.target.value }))
                }
                className="rounded-md border border-gray-300 px-3 py-2 text-sm"
              >
                {ROLES.map((role) => (
                  <option key={role.value} value={role.value}>
                    {role.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() =>
                  setEditForm((current) => ({ ...current, status: !current.status }))
                }
                className={`rounded-md border px-3 py-2 text-sm ${
                  editForm.status
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                    : "border-gray-200 bg-gray-50 text-gray-500"
                }`}
              >
                {editForm.status ? "활성" : "비활성"}
              </button>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setEditing(null)}
                className="rounded-md border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
              >
                취소
              </button>
              <button
                type="submit"
                disabled={updateUser.isPending}
                className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {updateUser.isPending ? "저장 중" : "저장"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
